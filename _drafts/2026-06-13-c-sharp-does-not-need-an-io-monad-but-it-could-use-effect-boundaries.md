---
title: "C# Does Not Need an IO Monad. It Needs Effect Boundaries."
date: 2026-06-13
description: "A case for separating deterministic decision logic from effectful boundaries in C# without importing a full IO monad."
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/), [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result/)

In Part 1, I wrote about how `List<T>` has a monadic structure.

In Part 2, I moved from lists to `Result<T>` in C#. Some of the feedback was fair: even when an abstraction is valid, it can still feel like it is being pushed into a language that does not really want it.

This post is about the smaller idea I still think survives.

Most C# code is not hard to read because it is object-oriented. It is hard to read because too many methods quietly depend on things that are not in their parameter list: `DateTime.UtcNow`, `Guid.NewGuid()`, `Random.Shared`, current culture, environment variables, databases, HTTP, logging, or mutable process state.

This is also not a new architecture. It is very close to Gary Bernhardt's Functional Core, Imperative Shell, Mark Seemann's impure/pure/impure sandwich, and the narrower pure-render-plus-effects rule React applies during render. What I am trying to do here is translate that pressure into ordinary C# constraints: no whole-language retrofit, no attempt to turn C# into Haskell, just better effect boundaries and better signaling.

Not:

> "C# should become Haskell."

Not:

> "Every method should return `IO<T>`."

Not even:

> "Every method should be pure."

The more useful claim is:

> A real C# program has to perform effects, but those effects do not need to swallow the whole program.

A database query is an effect. Reading the clock is an effect. Sending an email is an effect. Calling an HTTP API is an effect. Writing a log line is an effect. Mutating shared state is an effect.

Those things are not bad. They are what make programs useful.

The question is not whether effects should exist. They must. The question is whether the code that **decides what should happen** also needs to **make it happen** at the same time.

That distinction is where I think functional programming has something practical to offer C#.

---

## What "pure" means here

I am using "pure" in the strong engineering sense: for the same explicit inputs, a method returns the same result or exception, and it performs no observable interaction with the outside world.

That includes obvious things like file and network I/O, but also easy-to-miss ambient inputs like `DateTime.UtcNow`, `Guid.NewGuid()`, current culture, time zones, environment variables, and mutable static state.

That definition is stronger than the old Code Contracts wording of "no visible state changes," and that difference matters here because hidden inputs are exactly what make code hard to reason about.

---

## Effects are contagious

Bob Nystrom's article "What Color is Your Function?" is useful here, but only as an analogy. In C#, async is a real function color that the language and compiler track. `async` methods return `Task`, `Task<T>`, or another awaitable shape, and callers usually need to `await` them.

Effects have a similar shape.

```text
pure + pure = pure
pure + effectful = effectful
effectful + effectful = effectful
```

A pure function can call another pure function and remain pure.

But if a method reads the clock, queries the database, calls a web service, uses randomness, writes to a file, mutates a global variable, or sends an email, the containing method is now effectful.

For example:

```csharp
public static Money ApplyDiscount(Money price, decimal discount)
{
    return price * (1 - discount);
}
```

That method is pure. The result depends only on `price` and `discount`.

Now compare:

```csharp
public Money ApplyDiscount(Money price)
{
    var discount = _discountService.GetCurrentDiscount();
    return price * (1 - discount);
}
```

The multiplication is still deterministic, but the method is not. The discount is now a hidden input.

That does not make the method wrong. It may be perfectly reasonable application code. But it has a different shape from the first version. To understand its behavior, I need to know not only the `price`, but also the current state and behavior of `_discountService`.

C# makes async color visible in the type system. It does not usually make purity or effect color visible. That is the asymmetry I care about: one important property is compiler-tracked, and another important property is still mostly inferred socially by reviewers and maintainers.

This method:

```csharp
public Money CalculateTotal(Order order)
```

might be a pure calculation.

Or it might:

```text
read DateTime.UtcNow
query a tax service
read a feature flag
mutate a cache
log analytics
call an external API
throw depending on environment state
```

The signature does not say.

That is the hidden color I care about here.

---

## The point is containment, not purity everywhere

A real program has to touch the world.

It has to read files, query databases, call APIs, check the time, write logs, send messages, and mutate state. So the argument for pure functions cannot be "avoid effects." That would be useless advice.

The better argument is containment.

If a piece of code is primarily interacting with the world, let it be effectful.

If a piece of code is primarily deciding what should happen, try to make that decision a function of explicit inputs.

In other words:

```text
core:  decide what should happen
shell: make it happen
```

That is the basic idea behind Functional Core, Imperative Shell: keep computation dense and deterministic in the core, and keep I/O at the edges.

The functional core is not the whole application. The shell still exists. The shell is allowed to be imperative. The shell is where you query the database, call Stripe, send the email, publish the event, and return the HTTP response.

The point is that the decision does not always have to do those things itself.

---

## A mixed version

Consider a renewal flow:

```csharp
public async Task ProcessRenewal(Guid accountId)
{
    var account = await _accounts.Get(accountId);
    var invoices = await _invoices.GetRecent(accountId);
    var today = _clock.Today();

    if (account.Status == AccountStatus.Cancelled)
    {
        await _audit.Record(accountId, "Renewal skipped: cancelled");
        return;
    }

    if (invoices.Any(i => i.IsOverdue))
    {
        await _accounts.MarkPastDue(accountId);
        await _email.SendPaymentRequired(account.Email);
        return;
    }

    if (account.RenewalDate > today)
    {
        await _audit.Record(accountId, "Renewal skipped: not due yet");
        return;
    }

    await _billing.Charge(account.PaymentMethod, account.RenewalAmount);
    await _accounts.Extend(accountId, account.Plan.Duration);
    await _email.SendRenewalReceipt(account.Email);
}
```

This is not absurd code. It is the kind of code people write every day.

It is also doing several different things at once:

```text
fetch account
fetch invoices
read current date
decide whether renewal should happen
record audit messages
mark account past due
charge payment method
extend account
send email
```

The decision is mixed with the execution.

If you like Mark Seemann's phrase, this is close to an "impureim sandwich": the interesting business rule is trapped between effectful operations on both sides.

That mixture is sometimes fine. But it has a cost: there is no callable unit that means only this:

```text
Given this account, these invoices, this date, and this policy,
what should happen?
```

To ask that question, I have to run `ProcessRenewal`.

But running `ProcessRenewal` does not merely decide. It may update a database, send an email, charge a card, and write an audit record.

I can mock those things in a unit test, but then I am building a fake world around the method just to extract the decision.

Sometimes that is fine. Sometimes it is a smell.

---

## A separated version

Here is one way to split the decision from the execution:

```csharp
public abstract record RenewalDecision
{
    public sealed record Skip(
        Guid AccountId,
        string Reason) : RenewalDecision;

    public sealed record RequirePayment(
        Guid AccountId,
        string Email) : RenewalDecision;

    public sealed record Renew(
        Guid AccountId,
        string Email,
        PaymentMethod PaymentMethod,
        Money Amount,
        Duration Extension) : RenewalDecision;
}
```

`RenewalDecision` is data, which makes C# records a good fit here. They give you concise syntax and value-based equality, so tests can assert against whole decisions instead of hand-checking a pile of fields.

Now the policy can be a pure function:

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

The shell still does the effectful work:

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

And the execution logic can remain ordinary imperative C#:

```csharp
private async Task Execute(RenewalDecision decision)
{
    switch (decision)
    {
        case RenewalDecision.Skip skip:
            await _audit.Record(skip.AccountId, skip.Reason);
            break;

        case RenewalDecision.RequirePayment payment:
            await _accounts.MarkPastDue(payment.AccountId);
            await _email.SendPaymentRequired(payment.Email);
            break;

        case RenewalDecision.Renew renew:
            await _billing.Charge(renew.PaymentMethod, renew.Amount);
            await _accounts.Extend(renew.AccountId, renew.Extension);
            await _email.SendRenewalReceipt(renew.Email);
            break;
    }
}
```

This is not an IO monad.

It is not Haskell in C# clothing.

It is just this:

```text
facts -> decision
decision -> effects
```

The first half is deterministic. The second half is not.

That split is the whole point.

---

## This also lines up with DDD and CQRS

If you prefer enterprise architecture vocabulary, this split should look familiar.

In DDD terms, `DecideRenewal` is domain logic that stays persistence-ignorant. It does not know about repositories, HTTP clients, or SMTP servers. It just evaluates business rules.

In CQRS or event-driven code, an explicit decision object is also a useful boundary. The shell can translate that decision into database writes, outbound messages, domain events, or API responses.

This is not full event sourcing, and I am not claiming `RenewalDecision` should literally be stored as an event record. The smaller point is that once the outcome is explicit data, it becomes much easier to persist it, publish it, inspect it, replay it, or explain it.

It also fits ordinary dependency-injection-heavy C# just fine. The shell can stay as an injected application service or controller that talks to repositories, clocks, message buses, and HTTP clients. The core does not need the container at all; it just receives facts and returns a decision.

---

## Why this is useful

The usual argument for pure functions is that they are easier to test.

That is true, but I do not think it is the strongest argument. People can reasonably respond: "Just mock the dependencies."

The stronger argument is reviewability. Effect boundaries make hidden context visible, narrow the audit surface, and reduce how much code has to be trusted at once. One place reads context. One place decides. One place commits side effects.

Mocks are useful. I use them. But mocks are a testing technique, not a design property.

A mock can make a particular test run deterministic. It does not make the production method deterministic.

A pure decision function gives you something different: a production function whose meaning is already:

```text
explicit input -> explicit output
```

That enables more than unit testing.

It also changes the economics of testing. `DecideRenewal` needs no container setup and no mocks: instantiate the inputs, call the function, assert against the returned record. You can cover edge cases quickly in memory. The shell still needs tests, but because it mostly wires decisions to infrastructure, a smaller number of broader integration tests usually buys more than a large suite of interaction-heavy mock tests.

In practice, that often means two different test shapes:

```text
unit tests for the decision function
integration tests for the shell's wiring to infrastructure
```

The unit tests answer "given these facts, what decision should we get?" The integration tests answer "given this decision or branch, did we call the right database, billing, and messaging operations?" That split tends to produce faster tests, less brittle tests, and a clearer failure signal when something breaks.

It lets you safely ask questions.

```text
What would happen under the new renewal policy?
Which accounts would now be marked past due?
How many renewals would be skipped?
Would this historical account have produced a different decision?
Can I preview this operation before executing it?
Can I explain why the system made this decision?
Can I replay this production input locally?
```

With a pure decision function, those questions are ordinary function calls.

```csharp
var decision = RenewalPolicy.DecideRenewal(
    account,
    invoices,
    historicalDate,
    proposedPolicy);
```

With a mixed effectful method, those questions require a harness:

```text
fake database
fake billing system
fake email sender
fake clock
fake audit log
disabled side effects
special dry-run mode
```

At some point, the fake world exists because the decision was not separated from the effects.

---

## React already uses this idea

This is not only an academic functional-programming idea.

React has a localized version of the same rule. React says components and Hooks should be pure: same inputs should produce the same output, side effects should not run during render, and non-local values should not be mutated during render. React's docs also explicitly say side effects are necessary, but they should run outside render, commonly in event handlers or Effects.

That is a useful analogy because React does not say:

> "The whole application must be pure."

React says:

> "This phase must be pure."

Render should be pure because React may run rendering logic multiple times, pause it, resume it, prioritize it, or throw it away. React's docs specifically call out non-idempotent operations like `new Date()` and `Math.random()` as things that should not run during render.

That is an analogy, not a one-to-one transfer. React's rule is specifically about render semantics. My point is just that mainstream developers already accept the idea that some phases of a program are easier to reason about when effects are pushed out of them.

For backend C#, I think the analogous phase is often decision-making.

Not the whole application.

Not the database adapter.

Not the email sender.

Not the controller plumbing.

But the part that says:

```text
Given these facts, what should the program decide?
```

That part is often worth keeping pure.

---

## Pure does not mean "no local mutation"

One trap in these discussions is hearing that definition and assuming it means "never mutate anything anywhere."

It does not mean that.

This can still be pure:

```csharp
public static IReadOnlyList<int> SortedCopy(IReadOnlyList<int> input)
{
    var copy = input.ToArray();
    Array.Sort(copy);
    return copy;
}
```

The method mutates `copy`, but `copy` is local. The caller cannot observe the intermediate mutation.

This is different:

```csharp
public static void SortInPlace(int[] input)
{
    Array.Sort(input);
}
```

That mutates the caller's array. The mutation is externally observable.

So the useful distinction is not:

```text
mutation vs no mutation
```

It is:

```text
hidden inputs and externally observable outputs
```

A pure method should not depend on hidden inputs like the current time, global configuration, random number generators, database state, environment variables, or mutable static state.

It also should not produce hidden outputs like writing files, sending messages, mutating shared state, or changing arguments in a way the caller can observe.

---

## What about file reads?

This is where the definition matters.

Is this pure?

```csharp
string ReadConfig(string path)
{
    return File.ReadAllText(path);
}
```

Usually, no.

The result is not determined only by `path`. It also depends on:

```text
file contents
filesystem state
permissions
current working directory
encoding
whether another process is writing the file
whether the disk is available
```

But parsing the file contents can be pure:

```csharp
Config ParseConfig(string contents)
{
    return ConfigParser.Parse(contents);
}
```

The effectful shell reads the file.

The pure core parses the contents.

```csharp
var contents = File.ReadAllText(path);
var config = ParseConfig(contents);
```

If you model the file system as an explicit input, then the shape can become pure again:

```csharp
Config ReadConfig(FileSystemSnapshot fileSystem, string path)
{
    var contents = fileSystem.ReadAllText(path);
    return ConfigParser.Parse(contents);
}
```

That is not how ordinary C# usually works, but it shows the underlying idea: the issue is not that files are metaphysically impure. The issue is that ordinary file reads depend on hidden world state.

---

## What about bit flips?

Another objection is that even `1 + 1` depends on hardware. A CPU can have a bit flip. Memory can be corrupted. The process can be killed. The operating system can have a bug.

That is true, but it is not the level at which this distinction is useful.

Purity is a property relative to the execution model we are reasoning in.

Type safety also does not survive arbitrary memory corruption. That does not make type safety meaningless.

When I call this pure:

```csharp
public static int Add(int x, int y) => x + y;
```

I am not claiming the physical universe guarantees it under every possible hardware failure.

I am claiming that, within the normal semantics of the language and runtime, the method has no hidden inputs and no externally observable effects.

That is the level at which programmers usually reason about code.

---

## Where this pattern helps

The split is most useful when the code is primarily making a decision:

```text
pricing
eligibility
validation
authorization
fraud review
risk scoring
scheduling
retry policy
domain state transitions
approval workflows
```

For example:

```csharp
public static PaymentRetryDecision DecideRetry(
    PaymentFailure failure,
    int attemptsSoFar,
    LocalDateTime now,
    RetryPolicy policy)
{
    if (!failure.IsTransient)
        return PaymentRetryDecision.DoNotRetry("Failure is permanent");

    if (attemptsSoFar >= policy.MaxAttempts)
        return PaymentRetryDecision.DoNotRetry("Maximum attempts reached");

    var delay = policy.Backoff.CalculateDelay(attemptsSoFar);

    return PaymentRetryDecision.RetryAt(now.Plus(delay));
}
```

That function is useful because the returned value is meaningful.

It is a decision.

You can test it. You can log it. You can compare old and new policies. You can replay historical failures. You can ask what would happen without actually retrying a payment.

That is the kind of pure function I want more of.

This also pairs naturally with explicit success/failure types. If a decision can produce an expected domain failure, the core can return something like `Result<RenewalDecision, Error>` or `Either<Error, RenewalDecision>` instead of throwing. The point is the same: keep the outcome explicit, keep the inputs explicit, and let the shell decide how to turn that outcome into I/O.

You do not need a library for that, but libraries like LanguageExt or CSharpFunctionalExtensions can make this style less repetitive if your codebase already leans that way.

---

## Where this pattern does not help

This is not a rule to apply blindly.

Some code is just effectful by nature:

```csharp
public async Task SendWelcomeEmail(User user)
{
    await _email.Send(user.Email, Templates.Welcome);
}
```

Extracting a pure core here probably does not buy much.

Likewise:

```csharp
public async Task MarkUserAsSeen(Guid userId)
{
    await _users.MarkSeen(userId, _clock.UtcNow);
}
```

Maybe this is fine. There may not be a meaningful domain decision hiding inside it.

The rule I would use is:

> Keep code mixed when the effect is the point. Split code when the decision is the point.

A repository method is supposed to talk to the database.

An email sender is supposed to send email.

A logger is supposed to write logs.

A renewal policy, pricing rule, eligibility rule, retry rule, or fraud rule is usually not supposed to do those things. It is supposed to decide.

---

## Costs and tradeoffs

This pattern is not free.

You usually introduce more small types, more explicit data flow, and more handoff points between the shell and the core. That is often worth it, but it is still extra ceremony.

On hot paths, you should also be aware of allocation cost. If every request builds several intermediate records or DTOs just to shuttle data into and out of the core, that can matter at scale. Usually the right response is not "abandon the pattern," but "measure first, then optimize where it actually hurts." Sometimes the answer is simply fewer intermediate objects; sometimes it is a `record struct` or a different representation in one hot spot. But that is a measurement decision, not a first-principles decision.

If the real complexity in a service is query planning, transaction scoping, batching, or streaming, the pure kernel may stay small. That is fine. I am not suggesting those concerns get easier if you drag them into a fake pure pipeline.

In other words: use the pattern where it simplifies reasoning, but do not turn it into an absolute rule for every tiny method.

---

## What I am not claiming

I am not claiming every method should be pure.

I am not claiming functional code is automatically readable.

I am not claiming mocks are useless.

I am not claiming C# should imitate Haskell.

I am not claiming a pile of tiny functions is better than one clear imperative method.

I am not claiming local mutation is always bad.

I am not claiming an analyzer can prove full mathematical purity in arbitrary C#.

I am only claiming this:

> Hidden inputs and hidden outputs increase the amount of context needed to understand a method.

A pure function is the limiting case where the hidden input/output count is zero.

That is not always worth pursuing. But when the code represents an important decision, it often is.

---

## What about attributes and analyzers?

C# does not have a language-level effect system.

There is no built-in method annotation that means:

```csharp
pure OrderDecision DecideRenewal(...)
```

There are existing purity annotations. For example, .NET has `System.Diagnostics.Contracts.PureAttribute`, a leftover from the old Code Contracts work. Microsoft describes it as indicating that a type or method is pure in the sense that it does not make visible state changes, and analyzer CA1806 can use it to warn when the return value of a pure method is ignored. JetBrains also has a similar `PureAttribute` and related IDE inspections.

One caveat matters in practice: .NET's `PureAttribute` is itself marked `[Conditional("CONTRACTS_FULL")]`. For conditional attribute classes, the compiler only emits the attribute into metadata when that symbol is defined. So a bare `[Pure]` in an ordinary build may not survive compilation into assembly metadata at all. Depending on where a tool gets its information, that can make the annotation much weaker than it first appears.

Even without `[Pure]`, CA1806 still has some practical value because it can also be configured in `.editorconfig` to treat specific methods as "must use return value" APIs. That is useful for custom `Result<T>`, decision, and validation methods even if you are not trying to prove purity.

That is useful, but it is not the same as a full effect system, and it is also not the same as the stronger definition of purity I am using in this article.

For example, consider:

```csharp
[Pure]
public static DateTime CurrentTime() => DateTime.UtcNow;
```

This method may not visibly mutate state, but it is not deterministic. Calling it twice can produce different results.

So there are at least two related ideas:

```text
Does this method mutate visible state?
Does this method depend only on explicit inputs?
```

A method that does not mutate visible state is not necessarily pure in the stronger sense.

That is part of what makes this difficult in C#. A real purity analyzer has to be conservative. Part of the reason is that C# gives you many ways to hide effects:

```text
object aliasing
virtual and interface dispatch
delegates and callbacks
cross-assembly calls with incomplete metadata
mutation through reachable object graphs
```

If a method accepts an interface, the analyzer often cannot know which implementation will run. If it accepts a delegate, it cannot assume the callback is pure. If it mutates a locally created object, it has to prove that object was never aliased. Across assembly boundaries, it may have signatures and attributes, but not enough semantic information to prove much.

In practice, I would rather have a tool classify many methods as `Unknown` than incorrectly bless them as pure. Trust matters more than coverage here.

It can still catch obvious problems:

```text
DateTime.Now
DateTime.UtcNow
Guid.NewGuid()
Random.Shared
File.*
Console.*
Environment.*
HTTP calls
database calls
writes to fields
writes to static state
mutation of arguments
calls to unknown effectful methods
```

But it cannot magically prove every semantic property of arbitrary C#.

That does not make it useless.

Nullable reference types do not prove the absence of null bugs in every possible program either. They still make intent visible and catch a useful class of mistakes.

I would view purity attributes the same way:

```text
not a proof
not a replacement for design
not an IO monad
a lintable convention for keeping deterministic code deterministic
```

That is the role I would want something like Purely Sharp to play.

The same goes for custom Roslyn analyzers. A team can get real value from conventions like:

```text
no DateTime.UtcNow in decision-layer code
no repository calls in domain-policy methods
no Guid.NewGuid() inside deterministic rules
no implicit current-culture behavior in deterministic rules
```

That still would not be a proof of purity. But it would make the architecture more visible, catch common leaks early, and reduce how much review-time discipline has to do by hand.

---

## Where IO fits

The IO monad is one formal way to make effects explicit.

In Haskell, `IO` marks computations that interact with the outside world. That makes the effect boundary visible in the type. You do not have a method that looks like:

```text
Path -> string
```

while secretly reading the file system. The effect is part of the type.

That is an elegant idea.

But in ordinary C#, I would not reach first for this:

```csharp
IO<RenewalDecision> DecideRenewal(...)
```

That is probably the wrong shape for most C# codebases.

Part of the reason is ergonomic. Haskell has the language built around this style. Ordinary C# does not have higher-kinded types or computation expressions, so a full IO encoding quickly turns into wrapper types, `SelectMany`, and a lot of ceremony.

Part of the reason is also ecosystem fit. C# already has one successful narrow effect marker in `Task<T>`. That is enough to show the basic idea can work. But it is also a reminder that retrofitting a stronger effect distinction across the whole language and BCL would be much harder than just enforcing cleaner boundaries in application code.

The practical lesson I would take from `IO` is smaller:

> Do not pretend interaction with the world is the same thing as computing a value.

In C#, that does not have to mean encoding every effect in a monad.

It can simply mean:

```text
read from the world at the edge
turn the result into explicit input
make the decision in pure code
execute the decision at the edge
```

Or:

```csharp
var account = await _accounts.Get(accountId);
var invoices = await _invoices.GetRecent(accountId);
var today = _clock.Today();

var decision = RenewalPolicy.DecideRenewal(
    account,
    invoices,
    today,
    _policy);

await Execute(decision);
```

That is the C# version I would actually ship.

---

## The smaller idea that survived

After writing about monads in C#, I am less interested in asking:

> "Can I encode this abstraction in C#?"

I am more interested in asking:

> "What pressure was the abstraction trying to create?"

With `IO`, the pressure is to stop hiding effects.

With `Result<T>`, the pressure is to stop hiding expected failures.

With `Option<T>`, the pressure is to stop hiding absence behind `null`.

Those ideas can be valuable even when the full abstraction is not.

For effects, the idea I keep coming back to is this:

> Make important decisions deterministic when practical, and keep the nondeterministic work at the boundary.

That is not a new idea. It is not even a particularly exotic one. React applies a version of it to rendering. Functional programmers have talked about it for decades. Languages with effect systems go much further than C# can.

But I still think it is a useful question to ask in ordinary C# code:

```text
Is this method deciding, doing, or both?
```

If it is mostly doing, let it do.

If it is mostly deciding, consider making the inputs explicit and returning a decision.

That is the part of functional programming I think fits C# best: not turning everything into a monad, but preserving deterministic islands inside programs that still have to talk to the world.
