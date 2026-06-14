---
title: "What Does This C# Method Promise?"
date: 2026-06-13
description: "A C# method call is an act of trust: names and signatures tell part of the contract, but often hide failure modes, ambient inputs, effects, and caller obligations."
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/), [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result/)

When I call `DeleteCustomer(...)`, I expect deletion.

When I call `File.WriteAllText(...)`, I expect a file write.

When I call `TryParse(...)`, I expect ordinary failure to come back in the return value.

When I call `GetUserAsync(...)`, I expect something awaitable.

When I call `CalculateTotal(...)`, I expect a calculation.

C# programmers rely on those expectations constantly. Some are enforced by the compiler. Some are expressed by naming conventions. Some are documented. Some are only implied.

A method call is an act of trust.

A C# method signature is a partial contract.

It tells me the explicit parameter types and return type, and sometimes async or nullability information. It usually does not tell me whether the method reads ambient state, performs effects, throws, mutates visible state, depends on culture, checks the clock, uses randomness, or creates caller obligations.

In Part 2, I wrote about `Result<T>` in C#. I still think `Result<T>` is useful. But the broader lesson was not "put monads in C#." The broader lesson was that some behavior matters enough to appear in the method contract.

The problem is not impurity. Some methods exist to perform effects.

What am I allowed to assume when I call this method?

The problem is surprise: when a method's visible contract is smaller than its real contract, the caller has to recover the missing information from naming, documentation, tests, source code, or production experience.

The goal is not to make every method pure. The goal is to make important behavior obvious, explicit, or isolated.

## The Partial Contract

Take a method like this:

```csharp
Money CalculateTotal(Order order)
```

That signature looks simple.

At the call site, it looks like:

```text
Order -> Money
```

But the implementation could be this:

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

But it is not just a calculation.

So what does the method actually promise? A caller might still need to know whether it reads the clock, uses `CurrentCulture`, calls a tax API, mutates the order, writes to a cache, throws, requires its return value to be used, or returns a resource the caller must dispose.

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

Parameter types, return types, async return shapes, and nullable annotations all fall into this bucket.

That is an important precedent. [`Task<T>` and other async return types](https://learn.microsoft.com/en-us/dotnet/csharp/asynchronous-programming/async-return-types) change the shape of a method in a caller-visible way. [`string` versus `string?`](https://learn.microsoft.com/en-us/dotnet/csharp/fundamentals/null-safety/nullable-reference-types) does not change the runtime type, but it makes intent visible enough for analysis and warnings.

Annotations and warnings do not make the underlying problem disappear. They make the contract visible enough for tools and reviewers to reason about it.

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

Method names are an informal effect system for humans.

They tell us a lot. They do not tell us everything.

Names matter. `DeleteCustomer` is obviously effectful. No one expects it to be pure. That is consistent with [.NET design guidance](https://learn.microsoft.com/en-us/dotnet/standard/design-guidelines/names-of-type-members) that method names should usually be verbs or verb phrases.

The problem is not obvious effectful methods.

The problem is methods whose names suggest one contract while their implementations have another.

### 3. Hidden behavior

This is the interesting category: current culture, current time, randomness, service calls, database queries, argument mutation, cache writes, non-obvious exceptions, resource ownership, ignored return values, ambient authorization, and feature flags.

Here is the same idea in a compact table:

| Behavior | How visible is it in C#? | Example |
|---|---|---|
| Parameter types | Compiler-enforced | `Calculate(Order order)` |
| Return type | Compiler-enforced | `Money` |
| Async | Type-level / compiler-visible | `Task<Money>` |
| Nullability | Static-analysis-visible | `string?` vs `string` |
| Culture dependency | Often hidden; analyzer-detectable | `string.Format("{0:C}", amount)` |
| Exceptions | Usually documented, not type-level | `LoadCustomer(id)` |
| I/O | Often implied by name | `WriteAllText`, `SendAsync` |
| Time/randomness | Often hidden | `DateTime.UtcNow`, `Guid.NewGuid()` |
| Mutation | Sometimes implied by name | `Sort`, `Add`, `Remove` |
| Purity | Usually invisible | `CalculateTotal(order)` |
| Must-use return value | Usually invisible unless annotated | `TryParse`, pure calculations |
| Disposal responsibility | Type/convention/analyzer | `IDisposable`, `using` |

## Four Contract Gaps

The rest of the article uses four categories:

| Contract gap | Example | Why it matters | Possible signal |
|---|---|---|---|
| Failure | `LoadCustomer(id)` | Hidden control flow or output path | docs, analyzer, `Result<T>` |
| Ambient inputs | `string.Format("{0:C}", amount)`, `DateTime.UtcNow` | Output depends on hidden context | `IFormatProvider`, explicit time/value |
| Effects | DB, HTTP, file I/O, cache writes, in-place mutation | Hidden inputs or visible side effects | naming, boundaries, annotations |
| Caller obligations | ignored return value, undisposed resource, un-awaited task | Caller has extra responsibilities | annotations, conventions, analyzers |

That is enough to show the pattern without turning this into a catalog.

## What I Am Not Claiming

I am not claiming every method should be pure, dependency injection is bad, every exception should become `Result<T>`, C# should imitate Haskell, analyzers can prove arbitrary semantic properties, names and documentation are useless, or one clear imperative method should become ten tiny functions.

The claim is narrower: when a method has behavior callers must account for, that behavior should be obvious, explicit, or isolated.

```text
Obvious: DeleteCustomer deletes.
Explicit: FormatAmount(amount, culture) depends on culture.
Isolated: CalculateTotal(order, taxRate, discount) decides; CalculateTotalForCheckout gathers facts.
```

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

That means the visible contract is incomplete.

The hidden part is the alternate path.

In C#, exception behavior is real program behavior, but it is usually surfaced through documentation, naming, tests, analyzers, and conventions rather than through the type itself.

I am not arguing that every thrown exception belongs in the type. For exceptional failures, exceptions are often the right tool. But for expected outcomes that callers are supposed to handle, the method's name or return type should usually say so.

That is why these shapes create meaningfully different expectations:

```csharp
Customer LoadCustomerOrThrow(Guid id)
Customer? FindCustomer(Guid id)
bool TryLoadCustomer(Guid id, out Customer customer)
Result<Customer> LoadCustomer(Guid id)
```

The point is not that one shape is always right. The point is that expected failure should usually be visible somewhere: in the name, in the return type, or in documentation.

This is where Part 2 still matters. `Result<T>` is useful when expected failure should be visible to the caller. But the broader point is not "everything should become Result." The broader point is that failure behavior is part of the contract whether the signature admits it or not.

## Ambient Inputs: The Invisible Parameter

This method looks harmless:

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

```csharp
bool IsExpired(Subscription subscription)
{
    return subscription.ExpiresAt < DateTime.UtcNow;
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
        createdAt: DateTime.UtcNow);
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

The more interesting case is surprising behavior:

```csharp
CalculateTotal(order)     // calls tax API
ValidateUser(user)        // writes audit event
NormalizeName(name)       // reads database
FormatAmount(amount)      // depends on CurrentCulture
IsEligible(user)          // reads feature flag and current date
```

Applied to effects, "obvious, explicit, or isolated" means:

```text
Obvious: DeleteCustomer deletes.
Explicit: FormatAmount(amount, culture) depends on culture.
Isolated: CalculateTotal(order, taxRate, discount) decides; CalculateTotalForCheckout gathers facts.
```

## Purity Is One Strong Contract

This is where purity fits.

A pure method is not good because it is aesthetically functional. It is useful because it is the limiting case where the visible contract is close to the full contract:

```text
visible inputs in
visible output out
no hidden inputs
no externally visible side effects
```

In this article, "pure" means: for the same explicit inputs, the method has the same observable outcome and performs no externally observable interaction with the outside world.

That observable outcome may be a returned value or a deterministic failure. The important part is that the outcome does not depend on hidden state, time, randomness, I/O, or mutation visible to the caller.

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

## Functional Core / Imperative Shell As Contract Repair

Functional core / imperative shell is not a purity contest. It is a way to make the real inputs to important decisions visible.

It is also one way to repair a contract mismatch. The shell gathers ambient inputs and performs visible effects; the core takes explicit values and returns a calculation, decision, validation result, state transition, or plan.

Consider this checkout-style method:

```csharp
public async Task<Money> CalculateTotalForCheckout(Order order)
{
    var taxRate = await _taxService.GetRate(order.ShippingAddress);

    var discount = _featureFlags.IsEnabled("HolidayDiscount")
        ? await _discounts.Current()
        : Discount.None;

    return CheckoutMath.CalculateTotal(order, taxRate, discount);
}
```

The shell gathers facts from the world. The core decides with explicit inputs:

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

Use dependency injection in the shell. Use explicit values in the core.

## Caller Obligations

Some contracts are not about inputs or outputs. They are about what the caller now must do: use the return value, dispose the returned resource, or await the returned task.

If I ignore the result of a pure calculation, that may be a bug.

If I receive an `IDisposable` and fail to dispose it, that may leak resources.

If I call an async method and fail to await it where ordering matters, that may change behavior.

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

What it can do is catch obvious contract leaks: `DateTime.UtcNow`, `Guid.NewGuid()`, `Random.Shared`, implicit current-culture formatting, repository calls, HTTP calls, file I/O, field writes, static state writes, and mutation of arguments.

If a tool cannot classify something safely, I would rather it say `Unknown` than incorrectly bless the method as safe.

The goal is useful warnings, not theorem proving.

## A Note On Function Color

Bob Nystrom's ["What Color is Your Function?"](https://journal.stuffwithstuff.com/2015/02/01/what-color-is-your-function/) is useful here not because this article is about async, but because it shows that some method properties are not local implementation details. They change how callers compose with the method.

Async is the obvious C# example. A method returning `Task<T>` changes the call site: callers usually need `await`, a returned `Task<T>`, or an explicit blocking escape hatch.

Effects have a similar propagation shape, but a different consequence:

```text
Async color affects call mechanics.
Effect color affects trust.
```

C# colors asynchronous control flow. It does not usually color ambient inputs, visible mutation, I/O, or other effects.

## Why I Still Would Not Lead With An IO Monad

The deeper problem here is invisible behavior, not the lack of a monad. That is why I would not lead this conversation with `IO<T>`.

C# already has one successful marker for an important behavioral distinction: asynchronous control flow.

That is not the same as an effect system. But it shows that C# programmers are already used to some method behavior being visible at the call site.

So the practical goal is smaller than "every effect should become a monad": make time, culture, expected failure, return-value obligations, and important decision inputs visible where mistaken assumptions are costly.

## Restraint

I do not want C# codebases where every method is pure, every exception becomes `Result<T>`, every effect is wrapped in `IO<T>`, every method is annotated, and every dependency is forced into parameters. That would be a cure worse than the disease.

The bad version of this idea is easy to write:

```csharp
var a = Step1(input);
var b = Step2(a);
var c = Step3(b);
var d = Step4(c);
```

That is not better just because each step is pure. A pure function should still earn its name. `CalculateTotal`, `DecideRenewal`, `ValidatePolicy`, and `PlanShipment` are useful boundaries. `Step1` through `Step4` usually are not.

What I want is more modest. If a method deletes a customer, call it `DeleteCustomer`. If it depends on culture, make the culture explicit where the choice matters. If it reads the clock, ask whether `now` should be an input. If it has an expected failure mode, ask whether the caller should see that in the return type. If it is only calculating a decision, keep it away from the database, clock, and network if practical.

The goal is not to make every method pure. The goal is to make fewer method calls surprising.
