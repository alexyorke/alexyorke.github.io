---
title: "What Does This C# Method Promise?"
date: 2026-06-13
description: "A C# method call is an act of trust: names and signatures tell part of the contract, but often hide failure modes, ambient inputs, effects, and caller obligations."
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/), [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result/)

When I call `DeleteCustomer(...)`, I expect deletion.

When I call `File.WriteAllText(...)`, I expect a file write.

When I call `TryParse(...)`, I expect ordinary failure to be represented by the return value instead of an exception.

When I call `GetUserAsync(...)`, I expect something awaitable.

When I call `CalculateTotal(...)`, I expect a calculation.

C# programmers rely on those expectations constantly. Some are enforced by the compiler. Some are expressed by naming conventions. Some are documented. Some are only implied.

A method call is an act of trust: I usually do not inspect every callee before I call it. I rely on the method's name, type, documentation, conventions, and tooling to tell me what matters.

A C# method signature is a partial contract.

It tells me the explicit parameter types and return type, and sometimes awaitable or nullability information. It usually does not tell me whether the method reads ambient state, performs effects, throws, mutates visible state, depends on culture, checks the clock, uses randomness, or creates caller obligations.

That is not automatically a flaw. A method should hide implementation details. But it should not hide behavior the caller must account for.

By "contract", I do not mean every detail of the implementation. I mean the facts a caller needs to use a method correctly: what it needs, what it may do, how it may fail, and what obligations it leaves behind.

"Callers should not assume anything" sounds safe, but it cannot be how we actually program. A caller must assume something. The question is whether those assumptions are supported by the method's visible contract.

In Part 2, I wrote about `Result<T>` in C#. I still think `Result<T>` is useful. But the broader lesson was not "put monads in C#." The broader lesson was that some caller-relevant behavior matters enough to appear somewhere visible: name, type, documentation, analyzer, or boundary.

The problem is not impurity. Some methods exist to perform effects.

What am I allowed to assume when I call this method?

The problem is contract mismatch: when a caller has to account for behavior that is not visible in the name, type, documentation, convention, or boundary.

The goal is not to make every method pure. The goal is to make important behavior obvious, explicit, or isolated.

Purity is not about making C# functional. It is about preserving what callers are allowed to assume. If a method is pure, callers can usually repeat it, cache it, reorder it, retry it, run it later, or use it inside another abstraction without changing the meaning of the program. Once a method touches the world, some of those freedoms may disappear.

The useful part of the function-color idea is propagation. Async propagation changes how callers call a method. Effect propagation changes what callers can assume about a method. Those are different, but both are caller-relevant.

## The Partial Contract

Take a method like this:

```csharp
Money CalculateTotal(Order order)
```

By itself, that signature looks simple.

There is one important qualification: for instance methods, the receiver object is part of the contract too.

A method on `CheckoutService` carries different expectations from a method on `CheckoutMath`. Constructor-injected dependencies are not invisible in the same way as `DateTimeOffset.UtcNow`; they are visible at the object boundary.

So the issue is not that constructor injection is bad. The issue is whether the method lives at the right boundary.

If this lives in application-service code, orchestration is not very surprising:

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

The first method is orchestration. The second method is calculation. Both are useful. They are just making different promises.

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

So what does the method actually promise? A caller might still need to know whether it reads the clock, uses `CurrentCulture`, calls a tax API, mutates the order, writes to a cache, throws, requires its return value to be used, or returns a resource the caller must dispose.

Reading the source is always an option when you own the source and the code is nearby. But it is a poor substitute for a contract. We do not read the source of every method to know whether to `await` it, check for `null`, dispose the result, or handle ordinary parse failure. Some behavior is important enough to be visible without spelunking through the implementation.

This is especially true across boundaries: public APIs, packages, interfaces, generated clients, mocks, callbacks, and unfamiliar parts of a large codebase. The farther away the implementation is, the more the visible contract matters.

The parameter types are part of the contract.

The return type is part of the contract.

The method name is part of the contract.

But none of those necessarily tell the whole story.

## Three Visibility Levels

The basic issue is that method behavior is visible in different ways.

### 1. Compiler-visible behavior

Some behavior is directly visible to the compiler:

```csharp
Task<Customer> LoadCustomerAsync(Guid id)
Customer? FindCustomer(Guid id)
```

Parameter types, return types, awaitable return shapes, and nullable annotations all fall into this bucket.

That is an important precedent. [`Task<T>` and other async return types](https://learn.microsoft.com/en-us/dotnet/csharp/asynchronous-programming/async-return-types) change the shape of a method in a caller-visible way. [`string` versus `string?`](https://learn.microsoft.com/en-us/dotnet/csharp/fundamentals/null-safety/nullable-reference-types) does not change the runtime type, but it makes intent visible enough for analysis and warnings.

Annotations and warnings do not make the underlying problem disappear. They make the contract visible enough for tools and reviewers to reason about it.

This is not to say attributes are equivalent to language features. They are not. The analogy is weaker: C# already has a culture of making some contracts visible gradually, through signatures, annotations, warnings, and conventions.

### 2. Name-visible behavior

Some behavior is mostly visible by convention:

```csharp
DeleteCustomer(...)
SaveOrder(...)
WriteAllText(...)
SendAsync(...)
TryParse(...)
Dispose()
```

Method names are useful, but they are soft contracts.

Method names are one of the main ways C# code signals effects to humans.

They tell us a lot. They do not tell us everything.

Names matter. `DeleteCustomer` is obviously effectful. No one expects it to be pure. That is consistent with [.NET design guidance](https://learn.microsoft.com/en-us/dotnet/standard/design-guidelines/names-of-type-members) that method names should usually be verbs or verb phrases.

The problem is not obvious effectful methods.

The problem is methods whose names suggest one contract while their implementations have another.

### 3. Hidden behavior

This is the interesting category: current culture, current time, randomness, service calls, database queries, argument mutation, cache writes, non-obvious exceptions, resource ownership, ignored return values, ambient authorization, and feature flags.

These are not the same kind of behavior. The point of the table is not to merge them into one theory. It is to show that C# exposes some caller-relevant behavior strongly, some weakly, and some barely at all.

| Behavior | How visible is it in C#? | Example |
|---|---|---|
| Parameter types | Compiler-enforced | `Calculate(Order order)` |
| Return type | Compiler-enforced | `Money` |
| Async | Type-level / compiler-visible | `Task<Money>` |
| Nullability | Static-analysis-visible | `string?` vs `string` |
| Culture dependency | Often hidden; analyzer-detectable | `string.Format("{0:C}", amount)` |
| Exceptions | Usually documented, not type-level | `LoadCustomer(id)` |
| I/O | Often implied by name | `WriteAllText`, `SendAsync` |
| Time/randomness | Often hidden | `DateTimeOffset.UtcNow`, `Guid.NewGuid()` |
| Mutation | Sometimes implied by name | `Sort`, `Add`, `Remove` |
| Purity | Usually invisible | `CalculateTotal(order)` |
| Must-use return value | Usually invisible unless annotated | `TryParse`, pure calculations |
| Disposal responsibility | Type/convention/analyzer | `IDisposable`, `using` |

The useful question is not "can everything be compiler-visible?" It cannot. The useful question is whether a particular behavior is important enough to be moved from hidden to name-visible, type-visible, documented, analyzer-visible, or isolated behind a boundary.

## Four Contract Gaps

The rest of the article uses four categories:

| Contract gap | Example | Why it matters | Possible signal |
|---|---|---|---|
| Failure | `LoadCustomer(id)` | Hidden control flow or output path | docs, analyzer, `Result<T>` |
| Ambient inputs | `string.Format("{0:C}", amount)`, `DateTimeOffset.UtcNow` | Output depends on hidden context | `IFormatProvider`, explicit time/value |
| Effects | DB, HTTP, file I/O, cache writes, in-place mutation | Hidden inputs or visible side effects | naming, boundaries, annotations |
| Caller obligations | ignored return value, undisposed resource, un-awaited task | Caller has extra responsibilities | annotations, conventions, analyzers |

These categories are not morally equivalent. I group them only because they share one property: if the caller must account for them, hiding them makes the call harder to reason about.

## What I Am Not Claiming

I am not claiming:

- every method should be pure;
- dependency injection is bad;
- every exception should become `Result<T>`;
- C# should imitate Haskell;
- analyzers can prove arbitrary semantic properties;
- names and documentation are useless;
- one clear imperative method should become ten tiny functions.

The claim is narrower: behavior the caller must account for should be obvious, explicit, or isolated.

```text
Obvious: DeleteCustomer deletes.
Explicit: FormatAmount(amount, culture) depends on culture.
Isolated: CalculateTotal(order, taxRate, discount) decides; CalculateTotalForCheckout gathers facts.
```

There is also a tradeoff. Making hidden behavior visible often makes code more verbose. Passing `now`, `culture`, `taxRate`, or `discount` explicitly is not always worth it. The point is not to expose every dependency everywhere. The point is to expose the ones that materially affect correctness, repeatability, or caller obligations.

## Failure: The Invisible Alternate Path

Consider this signature:

```csharp
Customer LoadCustomer(Guid id)
```

It might return a `Customer`.

It might also throw:

```text
TimeoutException
DbException
OperationCanceledException
InvalidOperationException
UnauthorizedAccessException
```

If those failures are part of normal caller behavior, the visible contract is incomplete.

The hidden part is the alternate path.

In C#, exception behavior is real program behavior, but it is usually surfaced through documentation, naming, tests, analyzers, and conventions rather than through the type itself.

I am not arguing that every thrown exception belongs in the type. For exceptional failures, exceptions are often the right tool. But for expected outcomes that callers are supposed to handle, the method's name or return type should usually say so.

I do not mean every possible exception. Almost any code can fail catastrophically. The interesting case is expected failure that the caller is supposed to handle as part of normal control flow.

That is why these shapes create meaningfully different expectations:

```csharp
Customer LoadCustomerOrThrow(Guid id)
Customer? FindCustomer(Guid id)
bool TryLoadCustomer(Guid id, out Customer customer)
Result<Customer> LoadCustomerResult(Guid id)
```

The point is not that one shape is always right. The point is that expected failure should usually be visible somewhere: in the name, in the return type, or in documentation.

This is where Part 2 still matters. `Result<T>` is useful when expected failure should be visible to the caller. But the broader point is not "everything should become Result." The broader point is that failure behavior is part of the contract whether the signature admits it or not.

## Ambient Inputs: The Invisible Parameter

This method looks deterministic:

```csharp
string FormatAmount(decimal amount)
{
    return string.Format("{0:C}", amount);
}
```

It looks like:

```text
decimal -> string
```

But it is closer to:

```text
decimal + current culture -> string
```

The missing parameter is culture.

That is why [CA1305](https://learn.microsoft.com/en-us/dotnet/fundamentals/code-analysis/quality-rules/ca1305) exists. If an overload accepts `IFormatProvider` and you omit it, the runtime may use default culture behavior you did not intend.

A clearer version is:

```csharp
string FormatAmount(decimal amount, IFormatProvider culture)
{
    return string.Format(culture, "{0:C}", amount);
}
```

The usual repair is:

```text
make the hidden input explicit where the choice matters
```

Time and randomness work the same way.

This does not mean `DateTimeOffset.UtcNow` is forbidden. It means the boundary should be intentional. In UI display code, current culture may be exactly right. In persistence, signatures, tests, billing, scheduling, or cross-region behavior, the hidden input may need to be explicit.

```csharp
bool IsExpired(Subscription subscription)
{
    return subscription.ExpiresAt < DateTimeOffset.UtcNow;
}
```

This looks like:

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

The same applies to randomness and generated values:

```csharp
Invoice CreateInvoice(Order order)
{
    return new Invoice(
        id: Guid.NewGuid(),
        order: order,
        createdAt: DateTimeOffset.UtcNow);
}
```

versus:

```csharp
Invoice CreateInvoice(Guid id, Order order, DateTimeOffset createdAt)
{
    return new Invoice(id, order, createdAt);
}
```

The first method looks like:

```text
Order -> Invoice
```

But it also depends on a random ID source and the current time.

Ambient time and randomness are invisible parameters.

Sometimes that is fine. `CreateInvoice` may be the right boundary for ID and time generation. But if the caller needs repeatability, preview, replay, or policy comparison, those hidden parameters start to matter.

That is not mainly a functional-programming complaint. It is a determinism complaint. The real issue is what the caller has to trust.

The usual repair is the same in each case: make the hidden input explicit. Pass the value, pass the provider, or read once at the boundary and pass the value inward.

## Effects: Obvious Versus Surprising

Some effects are obvious from the name:

```csharp
DeleteCustomer(id)
SendEmail(message)
WriteAllText(path, contents)
SaveChanges()
```

Nobody expects those to be pure.

That is fine. The effect is the point.

The more interesting case is behavior that may be surprising depending on where the method lives:

```csharp
CheckoutService.CalculateTotalForCheckout(order) // calls tax API: unsurprising
PricingRules.CalculateTotal(order)               // calls tax API: surprising
ValidateUser(user)                               // writes audit event
NormalizeName(name)                              // reads database
FormatAmount(amount)                             // depends on CurrentCulture
IsEligible(user)                                 // reads feature flag and current date
```

## What Callers Are Allowed To Assume

The strongest reason to care whether a method is pure is not testing. It is what the caller is allowed to assume.

If a method is pure, callers usually have a lot of freedom:

```text
call it once
call it twice
cache the result
retry it
reorder it
run it later
run it in a dry run
run it in parallel
use it inside a higher-order function
```

Those freedoms come from the method's contract: explicit inputs in, explicit output out, no hidden inputs, no externally visible side effects.

Once a method reads the clock, calls a database, writes telemetry, mutates state, or sends a request, some of those freedoms may disappear.

That does not make the method bad. It means the method is making a different promise.

Purity is not the only useful contract. Idempotency, retry-safety, cache-safety, reorder-safety, and disposal responsibility are also contracts. The common point is that callers need to know which assumptions are valid.

## Where Effect Color Actually Bites

The propagation point becomes most concrete with retries and higher-order functions.

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

Purity is one way to make retry safe. Idempotency is another. They are different contracts, but both are caller-relevant. Microsoft's [Retry pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/retry) guidance makes the same point: before retrying, consider whether the operation is idempotent.

The same issue appears with higher-order functions:

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

But if the predicate writes telemetry, mutates a counter, reads the clock, or calls a service, then the implementation details become observable.

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
What order is it called in?
What happens if the result is enumerated twice?
Can the implementation short-circuit?
Could it be parallelized later?
```

Those questions matter much less when the predicate is pure. They matter a lot when the predicate has effects.

LINQ relies heavily on [deferred execution](https://learn.microsoft.com/en-us/dotnet/standard/linq/deferred-execution-lazy-evaluation), and [PLINQ](https://learn.microsoft.com/en-us/dotnet/standard/parallel-programming/potential-pitfalls-with-plinq) changes ordering and parallelism assumptions. Once callbacks have effects, evaluation strategy becomes caller-relevant.

## Purity Is One Strong Contract

This is where purity fits.

A pure method is not good because it is aesthetically functional. It is useful because it is the limiting case where the visible contract is close to the full contract:

```text
visible inputs in
visible output out
no hidden inputs
no externally visible side effects
```

I am using a practical, code-review definition of pure, not a formal semantics paper definition. For this article, a pure method is one whose observable behavior is determined by its explicit inputs and which does not produce externally observable effects.

A pure method can still be badly named, too large, slow, or unreadable. Purity is not a substitute for design.

It does **not** mean "never mutate anything anywhere."

This can still be pure:

```csharp
public static IReadOnlyList<int> SortedCopy(IReadOnlyList<int> input)
{
    var copy = input.ToArray();
    Array.Sort(copy);
    return copy;
}
```

This is different:

```csharp
public static void SortInPlace(int[] input)
{
    Array.Sort(input);
}
```

The first uses local mutation. The second changes caller-visible state.

So purity is one useful contract among many. It is the row where the hidden-behavior column is empty.

## One Repair Strategy: Functional Core / Imperative Shell

Functional core / imperative shell is not the thesis. It is one repair strategy. The thesis is that caller-relevant behavior should be obvious, explicit, or isolated.

Functional core / imperative shell is not a purity contest. It is a way to make the real inputs to important decisions visible.

It is also one way to repair a contract mismatch. The shell gathers ambient inputs and performs visible effects; the core takes explicit values and returns a calculation, decision, validation result, state transition, or plan.

This split has a cost. It introduces more names and more values flowing through the code. It is not worth doing for every endpoint or CRUD operation. I reach for it when the decision is important enough to name: pricing, authorization, eligibility, renewal, scheduling, validation, risk, or state transition logic.

The checkout example above is the split: `CheckoutService` gathers tax and discount facts from the world, and `CheckoutMath.CalculateTotal` calculates with explicit values.

The first method is allowed to know about the world. The second method should not have to.

That is not about making the whole system pure. It is about making the decision's real contract fit in the method signature.

It also gives a cleaner rule for dependency visibility:

| Code | Good place for dependency |
|---|---|
| Application service orchestration | Constructor-injected service |
| Repository / adapter | Constructor-injected connection or client |
| Domain policy / calculation | Explicit method parameter |
| Formatting for persistence | Explicit culture |
| Time-sensitive decision | Explicit `now` or clock value |
| Randomized decision | Explicit random value or generator |

So the rule is not "never use dependency injection." The rule is: choose the boundary where the dependency should be visible.

As a rule of thumb: use dependency injection for services that gather facts or perform effects; use explicit values for the facts a domain calculation or policy actually decides over.

## Caller Obligations

Some contracts are not about inputs or outputs. They are about what the caller now must do: use the return value, dispose the returned resource, or await the returned task.

If I ignore the result of a pure calculation, that may be a bug.

If I receive an `IDisposable` and fail to dispose it, that may leak resources.

If I call an async method and fail to await it where ordering matters, that may change behavior.

A lot of this already exists in fragments. That is the point. The ecosystem has already decided that some caller obligations are important enough for tooling.

This is why tools like `PureAttribute`, CA1806-style ignored-return checks, JetBrains `MustUseReturnValue`, and JetBrains `MustDisposeResource` fit this article's theme. They make caller obligations more visible.

## Attributes And Analyzers Can Help, But Not Prove Everything

I do **not** think attributes and analyzers are a replacement for language design.

They can be noisy. They can be incomplete. They can create false confidence.

But existing C# tooling already recognizes fragments of the hidden-contract problem:

- [CA1305](https://learn.microsoft.com/en-us/dotnet/fundamentals/code-analysis/quality-rules/ca1305) warns when code omits `IFormatProvider` where culture matters.
- [CA1031](https://learn.microsoft.com/en-us/dotnet/fundamentals/code-analysis/quality-rules/ca1031) warns against catching overly general exception types.
- [Microsoft exception guidance](https://learn.microsoft.com/en-us/dotnet/csharp/fundamentals/exceptions/exception-handling) says you should only catch exceptions when you understand why they might be thrown and can implement specific recovery.
- JetBrains annotations include [`Pure`](https://www.jetbrains.com/help/resharper/Reference__Code_Annotation_Attributes.html), `MustUseReturnValue`, and `MustDisposeResource`, all of which communicate extra method contracts to tooling.

That is evidence for the larger claim: some method behavior matters enough that tools already try to make it visible.

But C# already relies on gradual, opt-in contracts: nullable annotations, editorconfig severities, async naming, `IDisposable` conventions, `TryParse` conventions, and XML docs.

So I do not think it is strange to ask for stronger signals where mistaken assumptions are expensive.

The high-value places are not every method in the codebase. They are places where contract mismatch is costly: domain decisions, pricing calculations, authorization decisions, security-sensitive checks, serialization and formatting boundaries, public library APIs, methods whose return values must not be ignored, and methods that transfer disposal responsibility.

For example:

```csharp
[Pure]
public static RenewalDecision DecideRenewal(...)
```

An analyzer will not prove full semantic purity or complete exception behavior in arbitrary C#.

What it can do, in conservative cases, is catch obvious contract leaks: `DateTimeOffset.UtcNow`, `Guid.NewGuid()`, `Random.Shared`, implicit current-culture formatting, repository calls, HTTP calls, file I/O, field writes, static state writes, and mutation of arguments.

An incorrect annotation is worse than no annotation. If `[Pure]` becomes aspirational instead of checked, it becomes documentation that can lie.

One subtlety: "does not mutate visible state" is weaker than "pure." A method can avoid mutation and still read the clock or current culture. If a tool exposes these contracts, it should distinguish deterministic, no-observable-side-effects, and must-use-return-value rather than pretending they are the same.

If a tool cannot classify something safely, I would rather it say `Unknown` than incorrectly bless the method as safe.

The goal is useful warnings, not theorem proving.

## Why I Still Would Not Lead With An IO Monad

That is why I still would not lead this discussion with `IO<T>`. [Koka](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/koka-effects-2013.pdf) and [Flix](https://doc.flix.dev/effect-system.html) make these distinctions explicit in the type system. The useful C# question is narrower: what is worth borrowing short of turning the whole codebase into an effect system?

## Restraint

I do not want C# codebases where every method is pure, every exception becomes `Result<T>`, every effect is wrapped in `IO<T>`, every method is annotated, and every dependency is forced into parameters. That would be a cure worse than the disease.

Making behavior visible has a cost. More explicit inputs can mean more parameters, more names, and more plumbing. That cost is not always worth paying. I would pay it where mistaken assumptions are expensive: pricing, authorization, security, persistence formats, scheduling, policy decisions, public APIs, and resource ownership.

The bad version of this idea is easy to write:

```csharp
var a = Step1(input);
var b = Step2(a);
var c = Step3(b);
var d = Step4(c);
```

That is not better just because each step is pure. A pure function should still earn its name. `CalculateTotal`, `DecideRenewal`, `ValidatePolicy`, and `PlanShipment` are useful boundaries. `Step1` through `Step4` usually are not.

What I want is more modest. If a method deletes a customer, call it `DeleteCustomer`. If it depends on culture, make the culture explicit where the choice matters. If it reads the clock, ask whether `now` should be an input. If it has an expected failure mode, ask whether the caller should see that in the return type. If it is only calculating a decision, keep it away from the database, clock, and network if practical.

Behavior the caller must account for should be obvious, explicit, or isolated.

The goal is not to make every method pure. The goal is to make fewer method calls surprising.
