---
title: "What Does This C# Method Promise?"
date: 2026-06-13
description: "Method contracts often hide more than their signatures show, and pure methods preserve what callers are allowed to assume."
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/), [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result/)

In C#, a method signature tells you some things very clearly. It tells you parameter types and return types. Sometimes it also tells you about awaitable work or nullability.

It often does not tell you other things that matter just as much in practice. A method might throw. It might read the current time. It might use `CurrentCulture`. It might call a database, mutate shared state, or return a resource the caller now has to dispose.

That hidden part is what this post is about.

I do not mean that methods should expose every implementation detail. They should not. A method should hide implementation details. What it should not hide is behavior the caller has to account for.

That is what I mean by "contract" here. I mean the facts a caller needs in order to use the method correctly: what it needs, what it may do, how it may fail, and what obligations it leaves behind.

In Part 2, I wrote about `Result<T>` in C#. I still think `Result<T>` is useful. But the larger issue is broader than result types. It is about what a method promises to the caller, and how much of that promise is actually visible at the call site.

Some of this is already handled well in C#. Parameter types are visible. Return types are visible. `Task<T>` changes how a method is called. Nullable annotations make some assumptions visible enough for warnings and review.

Other behavior is much easier to miss. A method can look smaller and simpler than it really is.

That is why I keep coming back to a simple rule of thumb: behavior the caller must account for should be obvious, explicit, or isolated.

Purity matters here because it is one strong way to achieve that. A pure method does not read hidden state or perform externally visible effects. That gives the caller a different set of assumptions from the ones they get when a method touches the world.

Once a method reads the clock, uses ambient configuration, sends a request, or mutates shared state, some of those assumptions change. That is completely fine when the effect is the point. It matters when the caller has to discover that behavior by accident.

## A Method Signature Is Only Part Of The Contract

Take a method like this:

```csharp
Money CalculateTotal(Order order)
```

By itself, that looks like a calculation.

There is one qualification up front: for instance methods, the receiver object is part of the contract too.

A method on `CheckoutService` carries different expectations from a method on `CheckoutMath`. Constructor-injected dependencies are visible at the object boundary in a way that `DateTimeOffset.UtcNow` is not.

The real question is boundary placement: does this method live where orchestration belongs?

If this lives in application-service code, orchestration is unsurprising:

```csharp
public sealed class CheckoutService
{
    public async Task<Money> CalculateTotalForCheckout(Order order)
    {
        var taxRate = await _taxService.GetRate(order.ShippingAddress);

        var discount = _featureFlags.IsEnabled("HolidayDiscount")
            ? await _discounts.Current()
            : Discount.None;

        return CheckoutMath.CalculateTotal(order, taxRate, discount);
    }
}
```

If this lives in calculation code, the expectation is different:

```csharp
public static class CheckoutMath
{
    public static Money CalculateTotal(
        Order order,
        TaxRate taxRate,
        Discount discount)
    {
        return order.Subtotal
            .ApplyDiscount(discount)
            .ApplyTax(taxRate);
    }
}
```

The first method orchestrates. The second calculates. Both are useful. They are just making different promises.

The contract mismatch appears when a method positioned as a calculation actually performs orchestration:

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

Now the real shape is closer to:

```text
Order
+ tax service state
+ feature flag state
+ discount service state
+ possible service failures
+ latency
-> Money or exception
```

That is not automatically bad. It may be perfectly reasonable application-service code.

But it is no longer just a calculation. It is also orchestration.

So what does the method actually promise?

A caller might still need to know whether it reads the clock, uses `CurrentCulture`, calls a tax API, mutates the order, writes to a cache, throws, requires its return value to be used, or returns a resource the caller must dispose.

Reading the source is always an option when you own the source and the code is nearby. But it is a poor substitute for a contract. We do not read the source of every method to know whether to `await` it, check for `null`, dispose the result, or handle ordinary parse failure. Some behavior is important enough to be visible without spelunking through the implementation.

This is especially true across boundaries: public APIs, packages, interfaces, generated clients, callbacks, mocks, and unfamiliar parts of a large codebase. The farther away the implementation is, the more the visible contract matters.

The parameter types are part of the contract.

The return type is part of the contract.

The method name is part of the contract.

But none of those necessarily tell the whole story.

## Some Behavior Is Visible, Some Is Not

C# already makes some method behavior visible.

```csharp
Task<Customer> LoadCustomerAsync(Guid id)
Customer? FindCustomer(Guid id)
```

`Task<T>` and other awaitable return shapes change the way callers compose with a method. [`string` versus `string?`](https://learn.microsoft.com/en-us/dotnet/csharp/fundamentals/null-safety/nullable-reference-types) does not change the runtime type, but it makes intent visible enough for analysis, warnings, and review.

Names also carry expectations:

```csharp
DeleteCustomer(...)
SaveOrder(...)
WriteAllText(...)
SendAsync(...)
TryParse(...)
Dispose()
```

Method names are soft contracts. They are one of the main ways C# code signals effects to humans. `DeleteCustomer` is obviously effectful. No one expects it to be pure. That lines up with [.NET design guidance](https://learn.microsoft.com/en-us/dotnet/standard/design-guidelines/names-of-type-members) that method names should usually be verbs or verb phrases.

The interesting cases start when behavior matters to the caller but mostly stays hidden.

For example:

| Contract gap       | Example                                                    | Why it matters                               | Possible signal                    |
| ------------------ | ---------------------------------------------------------- | -------------------------------------------- | ---------------------------------- |
| Failure            | `LoadCustomer(id)`                                         | Hidden alternate path or hidden control flow | name, docs, `Result<T>`            |
| Ambient inputs     | `string.Format("{0:C}", amount)`, `DateTimeOffset.UtcNow`  | Output depends on hidden context             | `IFormatProvider`, explicit `now`  |
| Effects            | DB, HTTP, file I/O, visible mutation                       | The call may change or depend on the world   | naming, boundaries, annotations    |
| Caller obligations | ignored return value, undisposed resource, un-awaited task | The caller has work to do after the call     | analyzers, conventions, attributes |

These are different phenomena. I group them together only because they create the same kind of problem for the caller.

I am also not trying to turn every method into a pure function, or every exception into `Result<T>`, or every dependency into another parameter. The bar is lower than that. If a behavior matters to the caller, I want it to be obvious (`DeleteCustomer` deletes), explicit (`FormatAmount(amount, culture)` depends on culture), or pushed to an outer layer (`CalculateTotalForCheckout` gathers facts and `CalculateTotal` calculates).

There is a tradeoff here. More visible behavior often means more parameters, more names, and a little more plumbing. That is not always worth it. It is worth it when the hidden dependency affects correctness, repeatability, or caller obligations.

## Failure: The Hidden Alternate Path

Consider this signature:

```csharp
Customer LoadCustomer(Guid id)
```

It might return a `Customer`.

It might also throw because of timeouts, database/provider failures, cancellation, invalid state, or authorization problems.

In C#, exception behavior is real program behavior, but it is usually surfaced through documentation, naming, tests, analyzers, and conventions rather than through the type itself.

I am not arguing for checked exceptions or for putting every possible exception into the signature. Almost any code can fail catastrophically. The case I care about is expected failure that the caller is supposed to handle as part of normal control flow.

That is why these shapes create different expectations:

```csharp
Customer LoadCustomerOrThrow(Guid id)
Customer? FindCustomer(Guid id)
bool TryLoadCustomer(Guid id, out Customer customer)
Result<Customer> LoadCustomerResult(Guid id)
```

I do not think one of those shapes is always right. I do think expected failure should usually be visible somewhere: in the name, in the return type, or in documentation.

This is where Part 2 still matters. `Result<T>` is useful when expected failure should be visible to the caller. More generally, failure behavior is part of the contract whether the signature admits it or not.

## Ambient Inputs: The Hidden Parameter

Here is a simpler example:

```csharp
string FormatAmount(decimal amount)
{
    return string.Format("{0:C}", amount);
}
```

Its visible shape looks like this:

```text
decimal -> string
```

Its real shape is closer to this:

```text
decimal + current culture -> string
```

What is missing there is culture.

That is why [CA1305](https://learn.microsoft.com/en-us/dotnet/fundamentals/code-analysis/quality-rules/ca1305) exists. If an overload accepts `IFormatProvider` and you omit it, the runtime may use default culture behavior you did not intend.

A clearer version is:

```csharp
string FormatAmount(decimal amount, IFormatProvider culture)
{
    return string.Format(culture, "{0:C}", amount);
}
```

The same issue appears with time:

```csharp
bool IsExpired(Subscription subscription)
{
    return subscription.ExpiresAt < DateTimeOffset.UtcNow;
}
```

That looks like:

```text
subscription -> bool
```

But it is closer to:

```text
subscription + now -> bool
```

A clearer version is:

```csharp
bool IsExpired(Subscription subscription, DateTimeOffset now)
{
    return subscription.ExpiresAt < now;
}
```

Randomness and generated values work the same way:

```csharp
Invoice CreateInvoice(Order order)
{
    return new Invoice(
        id: Guid.NewGuid(),
        order: order,
        createdAt: DateTimeOffset.UtcNow);
}
```

That method is not just:

```text
Order -> Invoice
```

It also depends on a generated ID and the current time.

This does not make `DateTimeOffset.UtcNow`, `Guid.NewGuid()`, or `CurrentCulture` suspicious by default. Sometimes `CreateInvoice` is exactly the right boundary for ID and time generation. In UI display code, current culture may be exactly right.

The point is narrower than that. When repeatability, preview, replay, persistence, cross-region behavior, billing, scheduling, or policy comparison matters, the hidden input may need to become explicit.

This is really a determinism and caller-trust issue.

The fix is usually small:

```text
make the hidden input explicit where the choice matters
```

Pass the value. Pass the provider. Or read once at the boundary and pass the value inward.

## Effects: Obvious Versus Surprising

Some effects are obvious from the name:

```csharp
DeleteCustomer(id)
SendEmail(message)
WriteAllText(path, contents)
SaveChanges()
```

Nobody expects those to be pure, and that is fine. The effect is the point.

The more interesting case is behavior that is surprising for where the method lives:

```csharp
CheckoutService.CalculateTotalForCheckout(order) // calls tax API: unsurprising
PricingRules.CalculateTotal(order)               // calls tax API: surprising
ValidateUser(user)                               // writes audit event
NormalizeName(name)                              // reads database
FormatAmount(amount)                             // depends on CurrentCulture
IsEligible(user)                                 // reads feature flag and current date
```

This overlaps with ordinary advice like "separate responsibilities," but I am aiming at a slightly different question. Single responsibility is mostly about why code changes. Here I am talking about what the caller is allowed to assume.

A method can still have one clear responsibility and be effectful:

```csharp
DeleteCustomer(id)
SendEmail(message)
WriteAllText(path, contents)
```

Those methods are fine. The effect is the responsibility.

The trouble starts when a method positioned as a calculation, validation, or decision silently takes on effects that remove caller capabilities like retrying, caching, replaying, reordering, or dry-running.

## What Purity Preserves

Pure is not a moral category. It is just one strong contract in a broader picture.

For this article, a pure method is one whose observable behavior is determined by its explicit inputs and which does not produce externally observable effects. I mean that in a practical, code-review sense, not in the sense of a formal semantics paper.

A pure method is useful because it preserves some useful caller capabilities.

If a method is pure, callers can usually do things like this without changing the meaning of the program:

```text
call it once
call it twice
cache the result
retry it
reorder it
run it later
run it in a dry run
run it in parallel
replay it from recorded inputs
use it inside a higher-order function
```

They all come from the same underlying contract:

```text
explicit inputs in
explicit output out
no hidden inputs
no externally visible side effects
```

Once a method reads the clock, queries a database, writes telemetry, sends an email, charges a card, or mutates shared state, some of those capabilities may disappear.

That does not make the method bad. It just means the method is making a different promise.

## Retry, Idempotency, And Repetition

Consider retry logic:

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

If `operation` is a pure calculation, retrying is boring.

If `operation` writes telemetry, inserts a database row, creates an invoice, sends an email, or charges a card, retrying is no longer just "try again." It may duplicate an effect.

The type says:

```text
Func<T>
```

But the safety of `Retry` depends on another property:

```text
Is this operation safe to repeat?
```

Purity is one strong answer. Idempotency is another.

Idempotency belongs in the same family of caller-visible contracts.

Purity says:

```text
No externally visible effect.
```

Idempotency says:

```text
Repeating the effect is safe under the intended model.
```

A method can be effectful and idempotent:

```csharp
Task DeleteCustomer(Guid id)
```

Calling it twice may leave the system in the same intended state. That is useful. But it is a different promise from purity.

Both are caller-relevant contracts.

What matters is that the caller knows which assumptions are valid.

## Higher-Order Functions And Effect Color

Bob Nystrom's ["What Color is Your Function?"](https://journal.stuffwithstuff.com/2015/02/01/what-color-is-your-function/) is useful here for one reason: some method properties are not local implementation details. They propagate.

Async is the familiar C# example. A method returning `Task<T>` changes how I compose with it. Callers usually need `await`, a returned `Task<T>`, or an explicit blocking escape hatch.

Effects have a similar propagation shape, but a different consequence:

```text
Async propagation affects how I call the method.
Effect propagation affects what I am allowed to assume after the call.
```

C# gives awaitable work a caller-visible shape. It does not usually do the same for ambient inputs, visible mutation, I/O, idempotency, retry-safety, or other effects.

The analogy is strongest with higher-order functions:

```csharp
public static IEnumerable<Order> MatchingOrders(
    IEnumerable<Order> orders,
    Func<Order, bool> predicate)
{
    return orders.Where(predicate);
}
```

If `predicate` is pure, the implementation details of `MatchingOrders` mostly do not matter. The predicate is just:

```text
Order -> bool
```

But if the predicate logs, mutates state, reads the clock, or calls a service, then traversal details become caller-relevant:

```csharp
var matching = MatchingOrders(orders, order =>
{
    _audit.Record("Checked " + order.Id);
    return order.Total > 500;
});
```

Now the caller may need to know:

```text
Is the sequence lazy?
How many times is the predicate called?
What happens if the result is enumerated twice?
Can the implementation short-circuit?
Could it be parallelized later?
```

Those questions matter much less when the predicate is pure. They matter a lot when the predicate has effects.

That is the purity version of function color.

The callback's behavior changes what the caller is allowed to assume about the function that accepts it.

The same issue appears around parallelization. Once callbacks touch shared state, ordering, synchronization, and thread-safety become part of the contract.

## What Purity Does Not Promise

It is worth being precise here. Pure is a capability-preserving contract. It is not a capability-complete contract.

A pure method can still fail:

```csharp
public static int Divide(int x, int y)
{
    return x / y;
}
```

`Divide(10, 0)` is deterministic and has no side effects, but retrying it will not help.

A pure method can still be expensive:

```csharp
public static BigInteger Fibonacci(int n)
{
    return n <= 1
        ? n
        : Fibonacci(n - 1) + Fibonacci(n - 2);
}
```

Calling it twice does not change the world, but it may still be a bad idea.

A pure method may be semantically cacheable but still awkward to cache if its inputs are mutable or do not have stable equality.

A pure method can be badly named, too large, slow, or unreadable. Purity is not a substitute for design.

Purity removes one large class of things callers must account for: hidden inputs and externally visible effects. It does not guarantee totality, performance, stable equality, good naming, or thread safety.

Other contracts may still matter:

| Capability                               | Does purity alone guarantee it? | Extra contract needed                               |
| ---------------------------------------- | ------------------------------: | --------------------------------------------------- |
| Safe to repeat without duplicate effects |                         Usually | Strict purity                                       |
| Same explicit input gives same result    |                             Yes | Deterministic pure definition                       |
| Guaranteed to succeed                    |                              No | Totality, validation, `Result<T>`                   |
| Useful to retry                          |                              No | Transient failure model or idempotency              |
| Safe to cache                            |                          Partly | Stable equality, immutability, cache policy         |
| Cheap to call                            |                              No | Performance contract                                |
| Safe to reorder                          |                          Partly | Totality, no observed exceptions, algebraic laws    |
| Safe to parallelize                      |                          Partly | Immutability, thread-safety, no hidden shared state |
| Easy to understand                       |                              No | Good naming and design                              |

So I am not saying purity gives callers every useful guarantee. What it gives is one important guarantee:

```text
there is no hidden world interaction to account for
```

That is still valuable.

## One Repair Strategy: Functional Core / Imperative Shell

Functional core / imperative shell is not the whole thesis here. It is one practical response to the contract problem.

The shell gathers facts from the world and performs visible effects. The core takes explicit values and returns a calculation, decision, or plan.

The checkout example splits pretty naturally:

```text
CheckoutService
    reads tax rates and discounts from the world

CheckoutMath.CalculateTotal
    calculates from explicit inputs
```

The first method is allowed to know about the world. The second one usually should not have to.

That does not mean every method should become a pure domain function. It means important decisions often get easier to reason about when their real inputs are made explicit.

That also gives a practical rule for dependency visibility:

```text
Use dependency injection in the shell.
Use explicit values in the core.
Use constructor-injected clients in repositories and adapters.
Use explicit culture, now, IDs, and policy values in calculations and decisions where the choice matters.
```

This is a boundary-choice question. DI still fits naturally in the shell.

## Caller Obligations And Tooling

Some contracts are not about inputs or effects at all. They are about what the caller now has to do: use the return value, dispose the returned resource, or await the returned task.

That is why tools already recognize pieces of this problem:

* [CA1305](https://learn.microsoft.com/en-us/dotnet/fundamentals/code-analysis/quality-rules/ca1305) warns when culture is being chosen implicitly.
* [CA1031](https://learn.microsoft.com/en-us/dotnet/fundamentals/code-analysis/quality-rules/ca1031) warns against catching overly general exception types.
* [Microsoft's exception guidance](https://learn.microsoft.com/en-us/dotnet/csharp/fundamentals/exceptions/exception-handling) says you should catch exceptions only when you understand why they occur and can implement specific recovery.
* JetBrains annotations include [`Pure`](https://www.jetbrains.com/help/resharper/Reference__Code_Annotation_Attributes.html), `MustUseReturnValue`, and `MustDisposeResource`.

Nullable annotations are a useful precedent here. They do not prove runtime behavior. They make a contract visible enough for warnings, review, and tooling.

I think the same attitude makes sense elsewhere. An analyzer will not prove full semantic purity or complete exception behavior in arbitrary C#. What it can do, in conservative cases, is catch obvious contract leaks:

```text
DateTimeOffset.UtcNow
Guid.NewGuid()
implicit current-culture formatting
HTTP calls inside calculation code
mutation of arguments
ignored return values that look suspicious
```

That is still useful. In ordinary C# code, better signals matter more than theorem proving.

An incorrect annotation is worse than no annotation. If `[Pure]` becomes aspirational instead of checked, it becomes documentation that can lie.

If a tool cannot classify something safely, I would rather it say `Unknown` than incorrectly bless the method as safe.

## Why I Still Would Not Lead With IO

None of this is new in programming-language theory. Languages with effect systems, such as [Koka](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/koka-effects-2013.pdf) and [Flix](https://doc.flix.dev/effect-system.html), model some of these distinctions directly.

In ordinary C#, I would still not start by wrapping everything in `IO<T>`. The useful lesson is smaller. Interaction with the world and calculation are different promises, and some of that difference is worth making visible.

The practical C# question is not:

```text
How do I force every effect into a type?
```

It is:

```text
Which behaviors should be visible at the call site,
and which should be isolated behind a boundary?
```

## Restraint

I do not want C# codebases where every method is pure, every exception becomes `Result<T>`, every effect is wrapped in `IO<T>`, every method is annotated, and every dependency is forced into parameters.

That would be a cure worse than the disease.

Making behavior visible has a cost. More explicit inputs can mean more parameters, more names, and more plumbing. That cost is not always worth paying. Expose the dependencies that materially affect correctness, repeatability, or caller obligations.

This is also why the bad version of the idea is easy to spot:

```csharp
var a = Step1(input);
var b = Step2(a);
var c = Step3(b);
var d = Step4(c);
```

Breaking a method into `Step1`, `Step2`, `Step3`, and `Step4` does not help by itself. A pure function should still earn its name. `CalculateTotal`, `DecideRenewal`, `ValidatePolicy`, and `PlanShipment` are useful boundaries. `Step1` through `Step4` usually are not.

What I want is more modest.

If a method deletes a customer, call it `DeleteCustomer`.

If it depends on culture, make the culture explicit where the choice matters.

If it reads the clock, ask whether `now` should be an input.

If it has an expected failure mode, ask whether the caller should see that in the return type.

If it is only calculating a decision, keep it away from the database, clock, and network if practical.

Behavior the caller must account for should be obvious, explicit, or isolated.

The practical goal is fewer surprising method calls.
