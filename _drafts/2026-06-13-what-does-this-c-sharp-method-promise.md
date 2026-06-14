---
title: "What Does This C# Method Promise?"
date: 2026-06-13
description: "A C# method call is an act of trust: names and signatures tell part of the contract, but often hide failure modes, ambient inputs, effects, and caller obligations."
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/), [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result/)

When I call `DeleteCustomer(...)`, I expect deletion.

When I call `WriteAllText(...)`, I expect a file write.

When I call `TryParse(...)`, I expect ordinary failure to come back in the return value.

When I call `CalculateTotal(...)`, I expect a calculation.

C# programmers rely on those expectations constantly.

A method call is an act of trust.

A C# method signature is a partial contract.

In Part 2, I wrote about `Result<T>` in C#. I still think `Result<T>` is useful. But the broader lesson was not "put monads in C#." The broader lesson was that some behavior matters enough to appear in the method contract.

The problem is not impurity. The problem is contract mismatch.

What am I allowed to assume when I call this method?

If a method's visible contract suggests one thing while its actual behavior depends on hidden inputs, hidden outputs, hidden failure modes, or hidden effects, reasoning about the call gets expensive.

The visible contract and the real contract are often different sizes.

## The Partial Contract

Take a method like this:

```csharp
Money CalculateTotal(Order order)
```

That signature looks simple.

But what does it actually promise?

```text
Does it read the clock?
Does it use CurrentCulture?
Does it call a tax API?
Does it mutate the order?
Does it write to a cache?
Does it throw?
Does it require the return value to be used?
Does it allocate or dispose resources?
Does it enumerate an IEnumerable more than once?
```

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

That is an important precedent. Nullable annotations do not change runtime behavior, but they make part of the contract visible enough for tools and warnings. That is the same kind of move I am interested in for other hidden behavior.

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

Method names are our weakest effect system.

They tell us a lot. They do not tell us everything.

### 3. Hidden behavior

This is the interesting category.

```text
reads CurrentCulture
reads DateTime.UtcNow
uses Random.Shared
calls a service
queries a database
mutates an argument
writes a cache
throws a non-obvious exception
requires disposal
requires the return value to be used
uses ambient authorization context
reads feature flags
```

That is where this article lives.

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

I want to keep the rest of the article focused on four categories:

| Contract gap | Example | Why it matters | Possible signal |
|---|---|---|---|
| Failure | `LoadCustomer(id)` | Hidden control flow or output path | docs, analyzer, `Result<T>` |
| Ambient inputs | `string.Format("{0:C}", amount)`, `DateTime.UtcNow` | Output depends on hidden context | `IFormatProvider`, explicit time/value |
| Effects | DB, HTTP, file I/O, cache writes, in-place mutation | Hidden inputs or visible side effects | naming, boundaries, annotations |
| Caller obligations | ignored return value, undisposed resource, un-awaited task | Caller has extra responsibilities | annotations, conventions, analyzers |

That is enough to show the pattern without turning this into a catalog.

## Failure: The Invisible Alternate Path

Consider this signature:

```csharp
Customer LoadCustomer(Guid id)
```

It might return a `Customer`.

It might also throw:

```text
TimeoutException
SqlException
OperationCanceledException
InvalidOperationException
UnauthorizedAccessException
```

That means the visible contract is incomplete.

The hidden part is the alternate path.

In C#, exception behavior is real program behavior, but it is usually surfaced through documentation, naming, tests, analyzers, and conventions rather than through the type itself.

That is why these three shapes create meaningfully different expectations:

```csharp
Customer LoadCustomerOrThrow(Guid id)
Result<Customer> TryLoadCustomer(Guid id)
Customer? FindCustomer(Guid id)
```

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

The fix is:

```text
make the hidden input explicit
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

The same applies to randomness:

```csharp
Guid CreateId() => Guid.NewGuid();
```

versus:

```csharp
Invoice CreateInvoice(Guid id, Order order) => new(id, order);
```

Ambient time and randomness are invisible parameters.

That is not mainly a functional-programming complaint. It is a determinism complaint. The real issue is what the caller has to trust.

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

The rule I find most useful is:

> Effects should either be obvious, explicit, or isolated.

```text
Obvious: DeleteCustomer deletes.
Explicit: FormatAmount(amount, culture) depends on culture.
Isolated: DecideRenewal is pure; ExecuteRenewal performs effects.
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

In this article, "pure" means: for the same explicit inputs, a method returns the same result or exception, and it performs no observable interaction with the outside world.

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

Functional Core, Imperative Shell is not a purity contest. It is a way to make the real inputs to important decisions visible.

The basic split is:

```text
gather facts
make decision
perform effects
```

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

The shell gathers facts from the world.

The core decides with explicit inputs:

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

That is not about making the whole system pure. It is about making the real inputs to the decision visible.

It also gives a cleaner rule for dependency visibility:

| Code | Good place for dependency |
|---|---|
| Application service orchestration | Constructor-injected service |
| Repository / adapter | Constructor-injected connection or client |
| Domain policy / calculation | Explicit method parameter |
| Formatting for persistence | Explicit culture |
| Time-sensitive decision | Explicit `now` or clock value |
| Randomized decision | Explicit random value or generator |

So the rule is not "never use dependency injection."

The rule is:

> Choose the boundary where the dependency should be visible.

Use dependency injection in the shell. Use explicit values in the core.

## The Useful Part Of "What Color Is Your Function?"

The most useful part of Nystrom's red/blue function essay is not just "some functions are async." It is that some method properties are not local implementation details. They change how other code can call, compose, reuse, and reason about the method.

Async is the obvious C# example:

```csharp
User GetUser(Guid id)
Task<User> GetUserAsync(Guid id)
```

Once a method becomes async, callers usually have to acknowledge that with `await`, `Task<T>`, or some deliberate blocking escape hatch.

That is the propagation idea:

```text
sync + async = async
pure + impure = impure
```

But the analogy is not exact.

```text
Async color affects call mechanics.
Effect color affects trust.
```

With async, C# usually gives you a visible wrapper like `Task<T>`.

With effects, C# usually does not.

That is the interesting asymmetry:

> Async functions are colored in C#. Effectful functions usually are not.

## Caller Obligations

Some contracts are not about inputs or outputs. They are about what the caller now must do.

Common examples:

```text
must use the return value
must dispose the returned resource
must await the returned task
```

Those are all real method behavior.

If I ignore the result of a pure calculation, that may be a bug.

If I receive an `IDisposable` and fail to dispose it, that may leak resources.

If I call an async method and fail to await it where ordering matters, that may change behavior.

This is why tools like `PureAttribute`, CA1806-style ignored-return checks, JetBrains `MustUseReturnValue`, and JetBrains `MustDisposeResource` fit this article's theme. They make caller obligations more visible.

## C# Already Makes Some Behavior Visible

C# already has successful examples of gradual contract visibility.

Async is one. `Task<T>` changes the shape of a method in a caller-visible way.

Nullability is another. `string` versus `string?` does not change the runtime type, but it makes intent visible enough for analysis and warnings.

That is an important precedent.

Annotations and warnings do not make the underlying problem disappear. They make the contract visible enough for tools and reviewers to reason about it.

## Existing Tooling Already Knows About Pieces Of This

Existing C# tooling already recognizes fragments of the hidden-contract problem.

For example:

- [CA1305](https://learn.microsoft.com/en-us/dotnet/fundamentals/code-analysis/quality-rules/ca1305) warns when code omits `IFormatProvider` where culture matters.
- [CA1031](https://learn.microsoft.com/en-us/dotnet/fundamentals/code-analysis/quality-rules/ca1031) warns against catching overly general exception types.
- Microsoft exception guidance says you should only catch exceptions when you understand why they might be thrown and can implement specific recovery.
- JetBrains annotations include [`Pure`](https://www.jetbrains.com/help/resharper/Reference__Code_Annotation_Attributes.html), `MustUseReturnValue`, and `MustDisposeResource`, all of which communicate extra method contracts to tooling.

That is evidence for the larger claim:

> Some method behavior matters enough that tools already try to make it visible.

## What Attributes And Analyzers Can Reasonably Do

I do **not** think attributes and analyzers are a replacement for language design.

They can be noisy. They can be incomplete. They can create false confidence.

But C# already relies on gradual, opt-in contracts:

```text
nullable annotations
editorconfig severities
async naming
IDisposable conventions
TryParse conventions
XML docs
```

So I do not think it is strange to ask for stronger signals where mistaken assumptions are expensive.

For example:

```csharp
[Pure]
public static RenewalDecision DecideRenewal(...)
```

or, hypothetically:

```csharp
[Deterministic]
[NoObservableSideEffects]
public static RenewalDecision DecideRenewal(...)
```

An analyzer will not prove full semantic purity or complete exception behavior in arbitrary C#.

What it can do is catch obvious contract leaks:

```text
DateTime.UtcNow
Guid.NewGuid()
Random.Shared
implicit current-culture formatting
repository calls
HTTP calls
file I/O
field writes
static state writes
mutation of arguments
```

If a tool cannot classify something safely, I would rather it say:

```text
Unknown
```

than incorrectly bless the method as safe.

The goal is useful warnings, not theorem proving.

## Why I Still Would Not Lead With An IO Monad

The deeper problem here is invisible behavior, not the lack of a monad.

That is why I would not lead this conversation with `IO<T>`.

In languages built around it, an explicit `IO` distinction is elegant. In ordinary C#, retrofitting that distinction across the BCL and ecosystem would be unrealistic.

C# already has one successful narrow effect marker in `Task<T>`. That is useful. But many other important behaviors in .NET still look deceptively ordinary.

So the practical goal is smaller:

```text
make time visible
make culture visible
make expected failure visible when it matters
make return-value obligations visible
keep important decision logic away from ambient world state
```

That is a much more C#-native thesis than "every effect should become a monad."

## Restraint

I do not want C# codebases where every method is pure, every exception becomes `Result<T>`, and every effect is wrapped in `IO<T>`. That would be a cure worse than the disease.

I am also not proposing:

```text
a complete effect system for C#
annotating every method
forcing every dependency into parameters
replacing clear imperative code with function confetti
```

What I want is more modest:

If a method deletes a customer, call it `DeleteCustomer`.

If it depends on culture, make the culture explicit where the choice matters.

If it reads the clock, ask whether `now` should be an input.

If it has an expected failure mode, ask whether the caller should see that in the return type.

If it is only calculating a decision, keep it away from the database, clock, and network if practical.

The goal is not to make every method pure. The goal is to make fewer method calls surprising.
