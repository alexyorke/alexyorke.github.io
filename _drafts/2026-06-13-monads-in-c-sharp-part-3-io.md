---
title: "Monads in C# (Part 3): IO"
date: 2026-06-13
description: "IO lets code describe an effect before deciding where and how to run it."
permalink: 2026/06/13/monads-in-c-sharp-part-3-io/
---

**Previously in the series**: *List is a monad (Part 1)* and *Monads in C# (Part 2): Result*

In the previous parts, we looked at `List<T>`, `Maybe<T>`, and `Result<TSuccess, TError>`. These types do more than hold values. Through operations such as `Map`, `Bind`, and `SelectMany`, they take a function from us and decide how to apply it.

With `List<T>`, the function is applied to each element. With `Maybe<T>`, it may be skipped. With `Result<TSuccess, TError>`, it runs only after a successful previous step. The surrounding type owns part of the calling strategy, and that is usually the point.

This raises a question:

> What kind of function can I safely hand over?

The answer changes when the function is **effectful**. In this article, an effectful function is one that observes or changes something outside its explicit arguments and return value. Reading a file, querying a database, calling an HTTP service, observing the current time, writing a log entry, and mutating shared state are all effects in this sense.

Effects are ordinary parts of useful programs. The interesting question is how much control we keep when an effectful operation is passed into another abstraction. `IO` is one way to keep the operation composable until the part of the program that owns the calling strategy is ready to run it.

## Direct calls and handed-over calls

In ordinary direct-style code, the programmer usually owns the calling strategy.

```csharp
var template = File.ReadAllText(path);
var html = RenderInvoice(order, template, culture, issuedAt);

_emailGateway.Send(html);
```

The order is visible. The file is read before the invoice is rendered. The invoice is rendered before the email is sent.

If the file read requires retry logic, it can be placed around that read. If the email needs an idempotency key, the caller can attach one. If a transaction must commit before a message is published, the caller can make that sequence explicit.

A callback changes that relationship. Instead of invoking the function directly, we give it to something else, and that other code decides when to call it.

Consider a `foreach` loop over an in-memory collection:

```csharp
var totals = new List<Money>();

foreach (var order in orders)
{
    totals.Add(CalculateTotal(order));
}

PublishPricingCompletedEvent();
```

The call to `CalculateTotal` appears exactly where it runs. Assuming the loop completes, all totals have been calculated before the event is published.

Now compare that with `Select`:

```csharp
var totals = orders.Select(order =>
    CalculateTotal(order));

PublishPricingCompletedEvent();
```

`Enumerable.Select` uses deferred execution. The assignment creates an enumerable that remembers the source and selector, but the selector does not run until the result is enumerated. ([Microsoft Learn][1])

At the point where the event is published, no totals may have been calculated.

We can force evaluation:

```csharp
var totals = orders
    .Select(order => CalculateTotal(order))
    .ToList();

PublishPricingCompletedEvent();
```

The distinction is about control. In the loop, we wrote the invocation directly. With `Select`, we described a transformation and handed its invocation to another abstraction. That transfer is useful, and it is one of the reasons higher-order functions compose so well. It also means the function's contract matters.

## Sorting makes the handoff obvious

Sorting is an even clearer example because the algorithm, not the programmer, decides which calls to make.

```csharp
customers.Sort((left, right) =>
    string.Compare(
        left.LastName,
        right.LastName,
        StringComparison.Ordinal));
```

The programmer supplies a comparison function. The sorting algorithm chooses which elements to compare, in what order, and how many comparisons are needed.

That fits the usual comparer contract when the function answers a value question:

```text
Does left come before, after, or at the same position as right?
```

Now consider an effectful comparer:

```csharp
customers.Sort((left, right) =>
{
    _audit.Record($"Compared {left.Id} and {right.Id}");

    var leftScore = _riskService.GetScore(left.Id);
    var rightScore = _riskService.GetScore(right.Id);

    return leftScore.CompareTo(rightScore);
});
```

This compiles, and it may even appear to work. The awkward part is that the sorting algorithm now controls more than ordering. It also controls:

```text
how many audit records are written
which pairs are audited
how many service calls are made
whether the same customer is scored repeatedly
the order and frequency of those calls
```

Those concerns belong to the calling strategy around the service and audit operations. They are hard to reason about when they are hidden inside a comparer.

`List<T>.Sort` accepts a comparison delegate and uses an unstable sorting algorithm; equal elements are not guaranteed to retain their original order. More generally, the comparison schedule belongs to the sorting implementation rather than the caller. ([Microsoft Learn][2])

The usual repair is to obtain the scores under an explicit calling strategy before sorting:

```csharp
var scoredCustomers = new List<ScoredCustomer>();

foreach (var customer in customers)
{
    var score = RetryThrottled(() =>
        _riskService.GetScore(customer.Id));

    scoredCustomers.Add(
        new ScoredCustomer(customer, score));
}
```

The sort can then compare ordinary values:

```csharp
scoredCustomers.Sort((left, right) =>
    left.Score.CompareTo(right.Score));
```

The service calls can now be retried, throttled, cancelled, cached, or instrumented in a visible phase. Sorting is just an easy place to see the handoff: whenever another API calls our function, that API owns some part of when and how the function runs.

## The hidden input

Effectful callbacks care about calling strategy because the call itself may observe or change something outside the argument list.

A pure function can be understood as a mapping from explicit inputs to an output:

```text
Input -> Output
```

For this article, a function is pure enough when replacing a call with its result would not change the program's observable behavior.

```csharp
public static Money CalculateTotal(
    Order order,
    TaxRate taxRate,
    Discount discount)
{
    return order.Subtotal
        .ApplyDiscount(discount)
        .ApplyTax(taxRate);
}
```

The calculation receives everything it needs as values. The same `Order`, `TaxRate`, and `Discount` produce the same `Money`.

An effectful function has a larger real input:

```csharp
public Money CalculateTotal(Order order)
{
    var taxRate =
        _taxService.GetRate(order.ShippingAddress);

    return order.Subtotal.ApplyTax(taxRate);
}
```

The signature suggests:

```text
Order -> Money
```

The behavior is closer to:

```text
Order + World -> Money + World'
```

`World` is a model for whatever surrounding state the function may observe:

```text
current time
service availability
network state
authentication state
rate limits
database contents
configuration
cache contents
transaction state
shared mutable state
```

`World'` represents the world after the call. The operation may have consumed quota, written telemetry, populated a cache, changed a database, or affected an external system.

The explicit argument list describes only part of the operation.

Two calls can therefore have the same visible input but different real inputs:

```csharp
var first =
    _creditService.GetLimit(customer.Id);

var second =
    _creditService.GetLimit(customer.Id);
```

Conceptually:

```text
CustomerId + World0
    -> Timeout + World1

CustomerId + World1
    -> CreditLimit + World2
```

Both calls use the same `CustomerId`, but the surrounding state can differ. Calling an effect observes, and often changes, the world at a particular point in time.

## Effects propagate through composition

Suppose `CalculateTotal` itself is pure:

```csharp
public static Money CalculateTotal(
    Order order,
    TaxRate taxRate)
{
    return order.Subtotal.ApplyTax(taxRate);
}
```

This wrapper is still effectful:

```csharp
public Money CalculateTotalForCheckout(
    Order order)
{
    var taxRate =
        _taxService.GetRate(order.ShippingAddress);

    return CalculateTotal(order, taxRate);
}
```

The pure calculation leaves the service call in the larger workflow, so the combined operation still depends on the world.

The same applies in the other direction:

```csharp
var receipt = RenderReceipt(order, total);

_emailGateway.Send(receipt);
```

`RenderReceipt` may be pure. The whole workflow is effectful because it sends an email.

Once an effect appears inside a larger operation, the larger operation inherits it. A pure step cannot erase a service call, a clock read, or a write to shared state introduced elsewhere in the composition.

This is why effects tend to spread outward through a call graph. If a low-level helper reads the clock, every operation that depends on that helper becomes time-sensitive. If a policy queries a repository, every caller of that policy now depends on database availability. If a formatter reads mutable configuration, every caller becomes configuration-sensitive. The code may still be the right design, but the larger operation now needs an effect-aware calling strategy.

## What the calling strategy includes

For a pure function, calling it twice usually changes cost more than meaning.

```csharp
var first = CalculateTotal(
    order,
    taxRate,
    discount);

var second = CalculateTotal(
    order,
    taxRate,
    discount);
```

The second call may waste CPU, but it does not consume another rate-limit slot, send another email, write another row, or observe another clock time.

For an effectful function, the act of calling is part of the meaning.

The caller may need to know:

```text
when the operation runs
whether it runs at all
how many times it runs
how quickly calls are made
whether calls may overlap
which transaction is active
which token is used
whether repetition is safe
which failures should be retried
what happened before a failure
```

A generic function type rarely contains that information:

```csharp
Func<CustomerId, CreditLimit>
```

The type says nothing about rate limits, timeouts, retries, cancellation, idempotency, or transactions.

A generic function type can still be called just fine. It simply describes less than the real operational contract.

## Why immediate effects are awkward to compose

Consider an ordinary effectful helper:

```csharp
public CreditLimit GetLimit(CustomerId id)
{
    return _creditService.GetLimit(id);
}
```

The effect happens as soon as `GetLimit` is invoked.

If another function calls it internally:

```csharp
public Decision Decide(Customer customer)
{
    var limit = GetLimit(customer.Id);

    return CreditPolicy.Decide(customer, limit);
}
```

then `Decide` is also effectful. More importantly, the service call has already happened before the caller of `Decide` gets control back.

The caller can retry the entire `Decide` operation:

```csharp
var decision = Retry(() =>
    Decide(customer));
```

Sometimes that is the correct design. If the entire operation is idempotent, transactional, or safely repeatable, retrying the whole workflow can be simple and robust.

The caller cannot retroactively put a timeout around only `GetLimit`, throttle only that service call, replace only that effect with a test interpreter, or retry the read without also rerunning any earlier work inside `Decide`. By the time higher-level code receives the result, the effect has already happened.

## `IO` as a deferred effect

An `IO<T>` type changes that contract.

A function can return a description of work that may later produce `T`. The call creates a value that represents the effectful operation, while the actual interaction with the world is delayed until that value is interpreted.

Conceptually:

```csharp
public IO<CreditLimit> GetLimit(
    CustomerId id)
{
    return IO.Delay(() =>
        _creditService.GetLimit(id));
}
```

The exact API depends on the library. The important part is the type:

```text
CustomerId -> IO<CreditLimit>
```

Calling `GetLimit(id)` constructs a value describing an effect. The service call is still waiting inside that value.

This is the same distinction used by Haskell's `IO`: actions can be defined and composed without being invoked immediately, and the `IO` operations provide sequential composition of those actions. ([Haskell][3])

Because the effect has not happened yet, the caller can still transform its calling strategy.

In pseudocode:

```csharp
IO<CreditLimit> getLimit =
    GetLimit(customer.Id)
        .Retry(transientFailures)
        .Timeout(TimeSpan.FromSeconds(5))
        .WithCancellation(cancellationToken);
```

The caller can then compose the resulting value with pure logic:

```csharp
IO<Decision> program =
    getLimit.Map(limit =>
        CreditPolicy.Decide(customer, limit));
```

Or compose it with another effect:

```csharp
IO<Unit> program =
    from limit in getLimit
    let decision =
        CreditPolicy.Decide(customer, limit)
    from _ in SaveDecision(decision)
    select Unit.Value;
```

`Map` and `Bind` build a larger description from smaller ones. Execution is still delayed.

That is why `IO` can be a monad even though running an action twice may observe two different worlds. The monad laws concern how effect descriptions compose. They do not claim that the external world remains unchanged between separate executions.

The eventual service call is still effectful. The useful property is that the **description** of the operation can be passed around, transformed, and composed as an ordinary value.

## Why executing at the edge matters

With `IO`, "move effects to the edge" means that interpretation happens at the boundary that owns the calling strategy. Code deeper in the program can still construct and combine `IO<T>` values:

```csharp
public IO<Decision> BuildDecisionProgram(
    Customer customer)
{
    return GetLimit(customer.Id)
        .Map(limit =>
            CreditPolicy.Decide(customer, limit));
}
```

That function can itself be pure. Given the same customer, it constructs the same description of a program.

The boundary operation interprets or runs the description:

```csharp
var program =
    BuildDecisionProgram(customer);

var decision =
    await program.RunAsync(cancellationToken);
```

The boundary is valuable because it is the last point where the effect is still a value and has not yet touched the world. Before `Run`, higher-level code can still:

```text
add retry or backoff
add a timeout
provide cancellation
limit concurrency
attach an idempotency key
choose a transaction
add logging or tracing
replace the interpreter in a test
decide whether the operation should run at all
```

After `Run`, the effect has already happened, and those policies cannot be applied retroactively. Calling `Run` inside a helper gives up that leverage:

```csharp
public CreditLimit GetLimit(CustomerId id)
{
    return GetLimitIO(id).Run();
}
```

The function has converted a composable effect description into an immediate world interaction. Its caller can only wrap the entire helper invocation.

Returning the `IO` preserves control:

```csharp
public IO<CreditLimit> GetLimit(
    CustomerId id)
{
    return GetLimitIO(id);
}
```

Now the caller can decide how that effect should run before composing it with the rest of the program. The practical guideline is to construct and compose effect descriptions wherever they make sense, then interpret them at a boundary that owns the calling strategy.

## `Result` and `IO` solve different problems

`Result<TSuccess, TError>` makes an outcome explicit:

```csharp
Result<CreditLimit, CreditLimitError>
```

It answers:

```text
Did the computation succeed?
If not, what failure was reported?
```

`IO<T>` answers a different question:

```text
Has this world interaction happened yet?
```

An effectful operation that can fail may therefore have this shape:

```csharp
IO<Result<CreditLimit, CreditLimitError>>
```

The outer `IO` says that obtaining the result requires touching the world. The inner `Result` describes the outcome after that interaction occurs.

A method that returns `Result` directly may still have already touched the world:

```csharp
public Result<CreditLimit, CreditLimitError>
    GetLimit(CustomerId id)
{
    // The effect occurs before this method returns.
}
```

By the time the caller receives the `Result`, the world may already have been touched. With `IO<Result<...>>`, the caller can apply an effect policy before execution. For example, it might retry timeouts but leave business rejections alone, refresh an expired token, or stop after a rate-limit response. `Result` models the outcome, while `IO` keeps the act of obtaining that outcome available for composition.

## Functional core, imperative shell

This leads directly to functional core / imperative shell.

The shell owns world interaction:

```text
files
databases
HTTP calls
clocks
transactions
retries
cancellation
messages
logging
```

It observes the world and turns successful observations into ordinary values.

The core decides what follows from those values:

```csharp
public static CheckoutDecision Decide(
    Order order,
    TaxRate taxRate,
    Discount discount,
    InventoryStatus inventory,
    Instant now)
{
    var total = order.Subtotal
        .ApplyDiscount(discount)
        .ApplyTax(taxRate);

    if (!inventory.CanFulfill(order.Items))
    {
        return CheckoutDecision.Rejected(
            "Some items are unavailable");
    }

    if (discount.ExpiresAt <= now)
    {
        return CheckoutDecision.Rejected(
            "Discount has expired");
    }

    return CheckoutDecision.Approved(total);
}
```

The shell can build the effectful program:

```csharp
public IO<CheckoutDecision> DecideCheckout(
    Order order)
{
    return
        from now in Clock.UtcNow
        from taxRate in TaxService
            .GetRate(order.ShippingAddress)
            .Retry(transientFailures)
        from discount in Discounts
            .GetFor(order.CustomerId)
        from inventory in Inventory
            .Check(order.Items)
        select CheckoutPolicy.Decide(
            order,
            taxRate,
            discount,
            inventory,
            now);
}
```

The program is interpreted at the application boundary:

```csharp
var decisionProgram =
    DecideCheckout(order);

var decision =
    await decisionProgram.RunAsync(
        cancellationToken);
```

The core receives facts and calculates a decision. The shell owns the protocol used to obtain those facts, whether the tax rate came from a database, an HTTP service, a cache, a fixture, or a simulation.

## Putting it together

Higher-order functions let another abstraction call our function on our behalf. That is valuable because it removes repetitive control flow and makes programs easier to compose.

Pure callbacks generally tolerate that handoff because the interesting behavior lies in the returned value. Effectful callbacks have a larger operational contract: timing, repetition, concurrency, retries, cancellation, rate limits, transactions, and idempotency can all matter.

`IO<T>` gives that operational contract room to be handled before the world is touched. The program can build a description, compose it with other descriptions, add the calling strategy around it, and then run it at the boundary that owns those choices.

That is the reason IO tends to run at the edge. The edge is where the program finally commits to a particular interpretation of the effectful description and allows the world to change.

[1]: https://learn.microsoft.com/en-us/dotnet/api/system.linq.enumerable.select?view=net-10.0&utm_source=chatgpt.com "Enumerable.Select Method (System.Linq) - Microsoft Learn"
[2]: https://learn.microsoft.com/en-us/dotnet/api/system.collections.generic.list-1.sort?view=net-10.0&utm_source=chatgpt.com "List<T>.Sort Method (System.Collections.Generic)"
[3]: https://www.haskell.org/tutorial/io.html?utm_source=chatgpt.com "A Gentle Introduction to Haskell: IO"
