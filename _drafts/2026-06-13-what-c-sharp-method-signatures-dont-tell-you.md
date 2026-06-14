---
title: "What C# Method Signatures Don't Tell You"
date: 2026-06-13
description: "C# signatures show types, but often hide behavior: exceptions, culture, time, randomness, effects, mutation, disposal, and whether a return value must be used."
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/), [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result/)

In Part 2, I wrote about `Result<T>` in C#. Some of the feedback was fair: the abstraction can become more visible than the problem.

After that post, I think I was more interested in the shape of `Result<T>` than in the thing it was trying to fix.

The problem is not "how do we get monads into C#?"

The problem is:

> How do we make important method behavior visible?

C# method signatures tell us the explicit parameter and return types. They usually do not tell us whether the method throws, reads ambient state, depends on culture, mutates visible state, performs I/O, uses randomness, or is safe to ignore.

That is the theme of this post.

This is also not a new architecture. The underlying pressure is very close to Gary Bernhardt's Functional Core, Imperative Shell, Mark Seemann's impure/pure/impure sandwich, and the narrower pure-render-plus-effects split React uses during render. I am not claiming novelty here. I am trying to translate the idea into ordinary C# constraints and tooling.

## The Hidden Contract

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

The parameter and return types are part of the contract. They are not the whole contract.

That is the broader issue I care about now: hidden method contracts.

## Four Common Things C# Leaves Out

Here are four common examples:

| Hidden behavior | Example | Why it matters | Possible signal |
|---|---|---|---|
| Throws | `File.ReadAllText(path)` | Non-local control flow | docs, analyzer, `Result<T>` |
| Reads culture | `string.Format("{0:C}", amount)` | Output changes by locale | `IFormatProvider` |
| Reads time or randomness | `DateTime.UtcNow`, `Guid.NewGuid()` | Non-deterministic | pass time/value/generator explicitly |
| Performs effects or mutation | DB, HTTP, file I/O, cache writes, in-place mutation | hidden inputs or visible side effects | naming, boundaries, annotations, analyzers |

You can add more rows to that table. Disposal is another. Return values that must be used are another. Ambient configuration is another.

But those four are enough to show the pattern.

## Exceptions Are Hidden Outputs

Consider this signature:

```csharp
Customer LoadCustomer(Guid id)
```

It might return a `Customer`.

It might also throw:

```text
SqlException
TimeoutException
OperationCanceledException
InvalidOperationException
JsonException
UnauthorizedAccessException
```

The signature does not say.

That is not a minor implementation detail. Exceptions affect control flow, cleanup, retry logic, caller obligations, and what counts as a safe use site.

When an exception is thrown, the runtime searches up the call stack for a matching `catch`. If no appropriate handler is found, execution terminates with an error. So "can this method throw?" is part of the contract whether the signature admits it or not.

C# does not have checked exceptions. In ordinary C#, the exception contract is usually expressed through some mix of:

```text
documentation
naming
tests
conventions
analyzers
Result<T>-style types
code review
```

That is the natural bridge from Part 2.

I still think `Result<T>` is useful in some cases. But the broader lesson is not "use Result everywhere." The broader lesson is that expected failure is one more thing C# signatures often leave implicit.

## Culture Is a Hidden Input

This method looks harmless:

```csharp
string FormatPrice(decimal price)
{
    return string.Format("{0:C}", price);
}
```

But it has a hidden dependency: culture.

It is not really just:

```text
decimal -> string
```

It is closer to:

```text
decimal + current culture -> string
```

That matters because the output can change by locale, which can be correct for user display and wrong for persisted data or protocol text.

There is a reason analyzers like [CA1305](https://learn.microsoft.com/en-us/dotnet/fundamentals/code-analysis/quality-rules/ca1305) exist. When a method has an overload that accepts `IFormatProvider`, omitting it means the runtime may choose a default culture behavior you did not intend.

A clearer version is:

```csharp
string FormatPrice(decimal price, IFormatProvider culture)
{
    return string.Format(culture, "{0:C}", price);
}
```

That is the same philosophical move as purity, but more concrete:

```text
make the hidden input explicit
```

## Time and Randomness Are Hidden Inputs

This method also looks reasonable:

```csharp
bool IsExpired(Subscription subscription)
{
    return subscription.ExpiresAt < DateTime.UtcNow;
}
```

But `DateTime.UtcNow` is a hidden input.

So are:

```text
Guid.NewGuid()
Random.Shared
Environment.GetEnvironmentVariable(...)
CultureInfo.CurrentCulture
```

Those things make behavior non-deterministic or ambient in ways the signature does not show.

A clearer version is:

```csharp
bool IsExpired(Subscription subscription, DateTimeOffset now)
{
    return subscription.ExpiresAt < now;
}
```

Or, if you need the clock for multiple calls, read it once at the boundary and pass the value inward.

The same idea applies to randomness:

```csharp
Guid CreateInvoiceId() => Guid.NewGuid();
```

versus:

```csharp
Invoice CreateInvoice(Guid invoiceId, Order order) => new(invoiceId, order);
```

Again, the move is the same:

```text
stop treating ambient state as if it were not an input
```

## Purity Is One Strong Contract

This is where purity fits.

A pure method is not special because it is "functional." It is special because it makes a strong promise:

```text
explicit inputs in
explicit output out
no hidden inputs
no externally visible side effects
```

In this article, I am using "pure" in that strong engineering sense: for the same explicit inputs, a method returns the same result or exception, and it performs no observable interaction with the outside world.

That means obvious things like file and network I/O are out, but also hidden reads like `DateTime.UtcNow`, `Guid.NewGuid()`, current culture, and mutable static state.

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

The method mutates `copy`, but that mutation is local. The caller cannot observe the intermediate state.

This is different:

```csharp
public static void SortInPlace(int[] input)
{
    Array.Sort(input);
}
```

That mutates the caller's array. The mutation is part of the public behavior.

So purity is one useful row in the larger hidden-contracts table:

```text
Pure = no hidden inputs and no hidden outputs.
```

## One Practical Response: Keep The Middle Deterministic

One response to hidden method contracts is to keep more of the decision-making logic in code that does not quietly touch the world.

That is the idea behind Functional Core, Imperative Shell. I still think it is useful. I just no longer think "purity" is the only way to sell it.

Here is the shape:

```csharp
public async Task ProcessRenewal(Guid accountId)
{
    var account = await _accounts.Get(accountId);
    var invoices = await _invoices.GetRecent(accountId);
    var today = _clock.Today();

    var decision = RenewalPolicy.DecideRenewal(
        account,
        invoices,
        today,
        _policy);

    await Execute(decision);
}
```

The shell reads from the world:

```text
database
clock
configuration
message bus
HTTP
filesystem
```

The core decides:

```csharp
public static RenewalDecision DecideRenewal(
    Account account,
    IReadOnlyList<Invoice> recentInvoices,
    LocalDate today,
    RenewalPolicy policy)
{
    if (account.Status == AccountStatus.Cancelled)
        return new RenewalDecision.Skip(account.Id, "Account is cancelled");

    if (recentInvoices.Any(i => i.IsOverdue))
        return new RenewalDecision.RequirePayment(account.Id, account.Email);

    if (account.RenewalDate > today && !policy.AllowEarlyRenewal)
        return new RenewalDecision.Skip(account.Id, "Renewal is not due yet");

    return new RenewalDecision.Renew(
        account.Id,
        account.Email,
        account.PaymentMethod,
        account.RenewalAmount,
        account.Plan.Duration);
}
```

And the shell commits effects:

```text
charge card
update database
write audit record
send email
```

This does not make the whole program pure.

It makes one important contract stronger:

```text
given these facts, what should happen?
```

That is useful because it narrows the review surface. One place reads context. One place decides. One place commits side effects.

That is also why I now think reviewability is a stronger sales pitch than testability. Mocks can make tests deterministic. They do not make the production method itself easier to reason about.

## Existing Tooling Already Knows About Pieces Of This

This is not an imaginary category of concern. Existing C# tooling already warns about fragments of the hidden-contract problem.

For example:

- [CA1305](https://learn.microsoft.com/en-us/dotnet/fundamentals/code-analysis/quality-rules/ca1305) warns when you call an overload without `IFormatProvider` where one is available.
- [CA1031](https://learn.microsoft.com/en-us/dotnet/fundamentals/code-analysis/quality-rules/ca1031) warns against catching overly general exception types like `System.Exception`.
- `PureAttribute`-driven return-value analysis, including rules like CA1806, can treat ignored return values as suspicious when the method is understood to be side-effect free or semantically load-bearing.
- C# exception guidance says you should only catch exceptions when you understand why they might be thrown and can implement specific recovery. See [Microsoft's exception handling guidance](https://learn.microsoft.com/en-us/dotnet/csharp/fundamentals/exceptions/exception-handling).
- JetBrains annotations include [`Pure`](https://www.jetbrains.com/help/resharper/Reference__Code_Annotation_Attributes.html), `MustUseReturnValue`, `ContractAnnotation`, and disposal-related annotations like `MustDisposeResource`.

That is why I think the broader thesis is defensible:

> Method signatures often omit behavior that callers need to know, and existing tools already recognize parts of that problem.

## What Attributes And Analyzers Can Reasonably Do

I do **not** think attributes and analyzers are a replacement for language design.

They can be noisy. They can be incomplete. They can create false confidence. If overused, they can absolutely produce warning fatigue.

But C# already relies on gradual, opt-in contracts:

```text
nullable annotations
editorconfig severities
async naming
IDisposable conventions
TryParse conventions
XML docs
```

So I do not think it is strange to ask for stronger signals in places where correctness matters.

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

An analyzer cannot prove full mathematical purity in arbitrary C#.

It can still catch many obvious violations:

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

And if a tool cannot classify something safely, I would much rather it say:

```text
Unknown
```

than incorrectly bless the method as pure.

The practical goal is not theorem proving. The practical goal is to make intent visible and hidden behavior harder to miss.

## Why I Still Would Not Lead With An IO Monad

The deeper problem here is invisible behavior, not the lack of a monad.

That is why I would not lead this conversation with `IO<T>`.

In languages built around it, an explicit `IO` distinction is elegant. In ordinary C#, retrofitting that distinction across the BCL and ecosystem would be unrealistic.

C# already has one successful narrow effect marker in `Task<T>`. Async changes method shape in a way the type system can see. That is useful. But many other important behaviors in .NET still look deceptively ordinary.

So the practical goal is smaller:

```text
make time visible
make culture visible
make expected failure visible when it matters
make return-value obligations visible
keep important decision logic away from ambient world state
```

That is a much more C#-native thesis than "every effect should become a monad."

## Limits And Tradeoffs

This pattern is a bias, not a religion.

If the real complexity in a service is query planning, transaction scope, batching, streaming, or resource lifetime management, the pure kernel may stay small. That is fine.

The point is not to drag every concern into a fake pure pipeline.

The point is to extract the parts that are genuinely decisions from the parts that are genuinely interactions.

There is also real cost:

```text
more small types
more explicit data flow
more handoff points
sometimes more allocations
sometimes more annotations than the team can realistically maintain
```

That tradeoff can still be worth it. But it should be made deliberately.

## The Goal Is Not To Annotate Everything

I am not proposing:

```text
a complete effect system for C#
checked exceptions
annotating every method
forcing pure functions everywhere
replacing ordinary API design with attributes
```

I am proposing something narrower:

> Some hidden contracts matter enough that we should make them visible when correctness depends on them.

Sometimes the right move is a `Result<T>`.

Sometimes it is an extra parameter like `IFormatProvider` or `DateTimeOffset now`.

Sometimes it is a thinner shell around a deterministic core.

Sometimes it is just an analyzer warning that says "this method is reading current culture" or "you ignored a semantically load-bearing return value."

That is the part I still think survives from the monad discussion.

Not "turn C# into Haskell."

Just:

```text
make important behavior visible
```
