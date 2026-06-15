---
title: "What Can I Assume About This C# Method?"
date: 2026-06-13
description: "Types make assumptions about values explicit; purity makes assumptions about method calls explicit."
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/), [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result/)

Part 2 was about `Result<T>`. The part I still care about is visibility: expected failure changes what a caller can assume, and sometimes it is useful for that change to appear in the method contract.

This post is about the same idea applied to effects.

A caller cannot assume nothing. Every method call depends on some behavioral contract.

`DeleteCustomer(...)` is assumed to delete. `TryParse(...)` is assumed to represent ordinary failure in the return value. `GetUserAsync(...)` is assumed to produce awaitable work. `CalculateTotal(...)` is assumed to calculate a total.

If callers truly assumed nothing, ordinary APIs would become unusable. A method named `Sort` could delete files. A method named `FormatAmount` could send email. A predicate passed to `Where` could mutate the database.

Of course we do not program that way. We rely on names, types, documentation, conventions, and tooling to tell us what kind of behavior we are dealing with.

The question is whether those assumptions are supported by the method's visible contract.

The thesis is:

```text
Types make assumptions about values explicit.
Purity makes assumptions about calls explicit.
```

Purity says a call is value-like. Its observable behavior is determined by its explicit inputs, and it does not interact with the outside world.

That contract makes more caller transformations valid by default: repeat, retry, cache, reorder, replay, parallelize, and compose.

Effects are necessary. A useful program eventually sends the email, writes the row, reads the clock, calls the API, and mutates state. The important distinction is that effectful calls need a different contract. They may still be safe to retry, cache, parallelize, or reorder, but only when some other property makes that true: idempotency, retry-safety, cache-safety, thread-safety, transactionality, or an explicit effect boundary.

## Types For Values, Purity For Calls

Static types make assumptions about values visible.

A program can be written without static types, but the assumptions do not disappear. If I add two values, call `.Length`, index into a collection, or pass a value to a method, I am assuming those values support those operations.

Without types, those assumptions are still encoded in the program. They are just less explicit.

Purity is similar, but for calls rather than values.

When I retry a method, cache its result, call it twice, pass it to LINQ, run it in parallel, or move it earlier in the program, I am assuming something about the method's behavior.

I may not use the word "pure." I may say "this is just a calculation," "this is safe to retry," "this should not mutate anything," or "this predicate only checks a condition." Those are behavioral contracts.

By "pure" here, I mean the practical code-review version:

```text
explicit inputs in
explicit result out
no hidden inputs
no externally visible effects
```

That definition is intentionally ordinary. It is not trying to settle every formal question about referential transparency, exceptions, or the physical universe. It is a useful engineering promise: the call behaves like a calculation rather than an interaction.

## Transformations Need Contracts

Calling a method once is the simplest case.

Real programs often do more than call a method once. They transform the call:

```text
repeat it
retry it
cache it
delay it
reorder it
replay it
parallelize it
pass it into another abstraction
```

Those transformations are not automatically valid.

A retry helper assumes it is allowed to call the operation again. A cache assumes a previous result can be reused. A sorting routine assumes its comparer is consistent. A LINQ query assumes its predicate can be called according to the query's evaluation strategy. A parallel loop assumes either no shared mutation or synchronization that the caller has accounted for.

Purity is one contract that makes many of those assumptions valid by default.

That is the useful part. The value of purity is not that it sounds mathematically elegant. The value is that it preserves more legal moves for the caller.

## Number, Timing, And Order

Purity makes the number, timing, and order of calls less important.

For a pure method, calling it twice instead of once usually changes performance, not program meaning. Calling it now or later usually does not change the result. Reordering it with another pure method is usually harmless, aside from cost or deterministic failure.

For an effectful method, those details may be the whole point. Calling it twice may send two emails. Calling it later may read a different clock or database state. Reordering it may change persisted state.

So callers do not merely need to know "what value does this return?" They often need to know whether the number, timing, and order of calls are observable.

Consider these two calls:

```csharp
var total = CalculateTotal(order, taxRate, discount);
var invoice = CreateInvoice(order);
```

The first one looks like a calculation. The second one may allocate an invoice number, read the current time, persist a record, or publish an event. Those are different kinds of call, even if both return one value.

If I call `CalculateTotal` twice, I probably expect the same total twice.

If I call `CreateInvoice` twice, I probably expect two invoices unless the method's contract says otherwise.

## Retry, Idempotency, And Repetition

Retry logic makes the distinction concrete:

```csharp
public static T Retry<T>(Func<T> operation, int attempts)
{
    Exception? last = null;

    for (var i = 0; i < attempts; i++)
    {
        try
        {
            return operation();
        }
        catch (Exception ex)
        {
            last = ex;
        }
    }

    throw last!;
}
```

The type says:

```text
Func<T>
```

But the safety of `Retry` depends on another property:

```text
Is this operation safe to repeat?
```

If `operation` is a pure calculation, retrying is boring. Calling it again does not duplicate any external effect.

If `operation` writes telemetry, inserts a database row, creates an invoice, sends an email, or charges a card, retrying is no longer just "try again." It may duplicate an effect.

Purity is one strong answer. Idempotency is another.

For example, a payment operation can be safe to retry when it uses an idempotency key. That does not make the operation pure. It creates a different contract:

```text
This operation touches the world, but repeating the same request is safe.
```

That is a perfectly good contract. The important part is that callers need some contract before they transform the call.

## Higher-Order Functions And Effect Color

Bob Nystrom's [What Color is Your Function?](https://journal.stuffwithstuff.com/2015/02/01/what-color-is-your-function/) is useful here because it shows that a function property can escape local implementation detail. In his essay, the red/blue split eventually maps to asynchronous functions. Async/await improves the ergonomics, but awaitable work still has a caller-visible shape.

The C# analogy is not exact, but the propagation idea is useful:

```text
Awaitable work affects how I call and compose a method.
Effectful work affects which transformations are valid around the call.
```

The analogy is strongest with higher-order functions.

```csharp
public static IEnumerable<Order> MatchingOrders(
    IEnumerable<Order> orders,
    Func<Order, bool> predicate)
{
    return orders.Where(predicate);
}
```

If `predicate` is pure, `MatchingOrders` is mostly about values. The predicate is just:

```text
Order -> bool
```

But if the predicate logs, mutates state, reads the clock, calls a service, or sends telemetry, then traversal details become caller-relevant.

```csharp
var matching = MatchingOrders(orders, order =>
{
    _audit.Record("Checked " + order.Id);
    return order.Total > 500;
});
```

Now the caller may need to ask:

```text
Is the sequence lazy?
How many times is the predicate called?
Is it called once per order?
In what order?
What happens if the result is enumerated twice?
Can the implementation short-circuit?
Could it run in parallel later?
```

Those questions mostly do not matter when the predicate is pure. They matter a lot when the predicate has effects.

That is the purity version of function color. The type says `Func<Order, bool>`, but there are two very different contracts hiding behind that shape:

```text
Order -> bool
Order + hidden world state -> bool + hidden effects
```

C# does not distinguish those at the type level.

This shows up in ordinary library design too. A comparer passed to sorting code is expected to behave consistently. A hash function used by a dictionary is expected to be stable for the key while it is in the dictionary. A predicate passed to `Where` is usually expected to be a predicate, not a database mutation hidden inside a boolean.

```csharp
int Compare(Customer x, Customer y)
bool Equals(Customer x, Customer y)
int GetHashCode(Customer customer)
```

Those signatures are small, but the caller assumptions around them are large.

## A Method Signature Is Only Part Of The Contract

C# method signatures are useful. They tell us parameter types, return types, and awaitable shapes. Nullable annotations can also make some assumptions visible enough for warnings and review.

They usually do not tell us whether a method reads the clock, depends on `CurrentCulture`, calls a database, writes a file, mutates shared state, or leaves some other observable effect behind.

Take a method like this:

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

That method makes a fairly strong promise. Given the same `order`, `taxRate`, and `discount`, it behaves the same way. It does not need the current time. It does not need a feature flag. It does not call a service. It does not write anything anywhere.

Now compare it to this:

```csharp
public Money CalculateTotal(Order order)
{
    var taxRate = _taxService.GetRate(order.ShippingAddress);

    var discount = _featureFlags.IsEnabled("HolidayDiscount")
        ? _discounts.Current()
        : Discount.None;

    return order.Subtotal
        .ApplyDiscount(discount)
        .ApplyTax(taxRate);
}
```

The arithmetic is still familiar, but the contract is larger.

The first method is basically:

```text
Order + TaxRate + Discount -> Money
```

The second method is closer to:

```text
Order
+ tax service state
+ feature flag state
+ discount service state
+ latency
+ possible service failures
-> Money or exception
```

That does not make the second method wrong. It may be exactly what you want in application-service code. The returned `Money` is no longer the whole story.

The receiver object matters. A method on `CheckoutService` carries different expectations from a method on `CheckoutMath`. Constructor-injected dependencies are visible at the object boundary in a way that `DateTimeOffset.UtcNow` or `Guid.NewGuid()` inside a calculation are not.

So the useful question is:

```text
Can the caller treat this method as just a calculation?
```

If the answer is yes, the method is easier to move around, reuse, and compose. If the answer is no, the caller has to account for something beyond the returned value.

## Hidden Inputs And Expected Failure

Impurity is not only about writes. It is also about hidden reads.

This method looks deterministic:

```csharp
string FormatAmount(decimal amount)
{
    return string.Format("{0:C}", amount);
}
```

But it is not really just:

```text
decimal -> string
```

It is closer to:

```text
decimal + current culture -> string
```

The same thing happens with time:

```csharp
bool IsExpired(Subscription subscription)
{
    return subscription.ExpiresAt < DateTimeOffset.UtcNow;
}
```

That is not really just:

```text
Subscription -> bool
```

It is closer to:

```text
Subscription + now -> bool
```

The usual repair is to make the hidden input explicit where the choice matters:

```csharp
bool IsExpired(Subscription subscription, DateTimeOffset now)
{
    return subscription.ExpiresAt < now;
}
```

Sometimes `CurrentCulture`, `UtcNow`, or `Guid.NewGuid()` are exactly what you want at that boundary. Sometimes they are not. The distinction matters when the caller needs repeatability, preview, replay, comparison, or a stable cache key.

Expected failure is another contract that may or may not be visible.

```csharp
Customer LoadCustomerOrThrow(Guid id)
Customer? FindCustomer(Guid id)
bool TryLoadCustomer(Guid id, out Customer customer)
Result<Customer> LoadCustomerResult(Guid id)
```

Those shapes create different expectations. The point is not that one is always right. The point is that normal caller behavior should usually be visible somewhere: in the name, in the return type, in documentation, or in the boundary where the method lives.

## What Purity Does Not Promise

Purity is a strong contract, but it is not the whole contract.

It is capability-preserving, not capability-complete.

A pure method can still fail:

```csharp
public static int Divide(int x, int y)
{
    return x / y;
}
```

It can still be expensive:

```csharp
public static BigInteger Fibonacci(int n)
{
    return n <= 1
        ? n
        : Fibonacci(n - 1) + Fibonacci(n - 2);
}
```

It can still be awkward to cache if its inputs are mutable or do not have stable equality.

So "pure" does not mean cheap, total, thread-safe, well-named, or automatically easy to use. It means the method's observable behavior is determined by explicit inputs and does not produce externally visible effects.

That is already a useful guarantee.

## One Repair Strategy: Functional Core / Imperative Shell

Functional core / imperative shell is one practical response to the contract problem.

The shell gathers facts from the world and performs visible effects. The core takes explicit values and returns a calculation, decision, or plan.

The shell can know about services:

```csharp
public async Task<Money> CalculateTotalForCheckout(Order order)
{
    var taxRate = await _taxService.GetRate(order.ShippingAddress);
    var discount = await _discounts.Current();

    return CheckoutMath.CalculateTotal(order, taxRate, discount);
}
```

The core can stay small:

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

The first method is allowed to know about the world. The second one usually should not have to.

This gives a practical dependency rule:

```text
Use dependency injection in the shell.
Use explicit values in the core.
```

Constructor injection is appropriate for application services, repositories, adapters, clients, and orchestration code. Explicit method parameters are often better for domain policy, pricing, validation, authorization, scheduling, retry rules, and other code where the main job is to decide.

This is not a rule for every method. It is a way to keep important decisions value-like when the surrounding program still needs to interact with the world.

## Tooling Can Help, But Not Prove Everything

C# already makes some behavior visible. Parameter types are visible. Return types are visible. `Task<T>` and other awaitable shapes change how a method is called. Nullable annotations make some assumptions visible enough for warnings without changing runtime behavior.

Purity usually is not visible in the type.

So we express it indirectly:

```text
naming
documentation
boundaries
tests
code review
analyzers
```

Annotations and analyzers can help in narrow cases. They can catch obvious leaks, warn on ignored return values, flag implicit culture usage, or encode project conventions. They cannot prove every semantic property of arbitrary C#.

That is fine. Nullable reference types do not prove the absence of every null bug either. They still make useful assumptions more visible.

I would rather have a conservative tool say `Unknown` than have it incorrectly bless a method as pure. The point of tooling is not certainty. The point is to make important contracts easier to see and easier to review.

## Restraint

The bad version of this idea is easy to write:

```csharp
var a = Step1(input);
var b = Step2(a);
var c = Step3(b);
var d = Step4(c);
```

That is not better just because each step is pure. A pure function should still earn its name. `CalculateTotal`, `DecideRenewal`, `ValidatePolicy`, and `PlanShipment` are useful boundaries. `Step1` through `Step4` usually are not.

There is also a tradeoff. Making behavior visible can make code more verbose. Passing `now`, `culture`, `taxRate`, or `discount` explicitly is not always worth it. The point is to expose the dependencies that materially affect correctness, repeatability, reuse, or caller obligations.

I would not annotate every method. I would not force every dependency into parameters. I would not turn clear imperative code into function confetti.

Effects belong in C# programs. They belong in the parts of the program where the caller expects interaction with the world.

Pure methods and effectful methods make different promises. Pure methods are value-like. Effectful methods are interaction-like. Both are useful, but they preserve different caller assumptions.

The goal is not to make every method pure. The goal is to know which assumptions remain valid before a method call becomes surprising.
