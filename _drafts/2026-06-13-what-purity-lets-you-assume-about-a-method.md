---
title: "What Purity Lets a Caller Assume"
date: 2026-06-13
description: "Types make assumptions about values explicit. Purity does something similar for method calls."
---

A caller always assumes something. If I call `DeleteCustomer(...)`, I assume it deletes. If I call `TryParse(...)`, I assume ordinary failure is reported through the return value. If I call `GetUserAsync(...)`, I assume I have awaitable work. If I call `CalculateTotal(...)`, I assume I have a calculation. Names, types, documentation, conventions, and tooling tell me what kind of call I am dealing with.

One part of a method contract that signatures often omit is whether a call is value-like or interaction-like. This is close to command-query separation, but my emphasis is a little different: I am asking what guarantees the caller gets when a call behaves like a calculation. The examples use C#-style syntax, but the point is broader.

This is not an argument that ordinary procedural code is broken. A lot of it is direct and truthful: read input, do work, write output, return. Purity matters most in methods callers want to treat like calculations.

By "impurity," I mean the call depends on more than its explicit inputs or produces more than its returned value. That includes visible effects like writing a file or sending an email, and hidden inputs like reading the clock, using current culture, or depending on global configuration. There is also always an observation boundary. In this post, "observable" means behavior that callers, tests, users, operators, or other systems may reasonably depend on.

The core claim is simple: types make assumptions about values explicit. Purity does something similar for calls. A pure call is value-like: when it returns normally, the same explicit inputs produce the same returned value, and the call leaves no externally visible effects behind. For an instance method, the receiver's observable state is part of that story too. Totality, exception behavior, cancellation, and cost are separate guarantees.

That contract makes some caller transformations less dangerous: repeat the call, duplicate it, cache it, reorder it, parallelize it, or compose it with other calculations. In languages with observable reference identity, such as C#, this assumes the result is being treated as a value. Effects are still necessary. Real programs eventually send the email, write the row, read the clock, call the API, and mutate state. The practical question is simple: what can the caller safely do with this method call?

## When the assumption matters

Imagine this code:

```csharp
var normalized = NormalizeOrder(order);
var total = CalculateTotal(normalized);
var label = FormatTotal(total);
```

Most of the time, informal evidence is enough. From names, location, and convention, `NormalizeOrder`, `CalculateTotal`, and `FormatTotal` look like calculations. If that inference is correct, the caller has room to move. I can call `CalculateTotal` twice while debugging, cache `FormatTotal`, replay the sequence with recorded inputs, or move the calculation into a test, a dry-run path, or a background validation job.

Now change the contract behind the same names:

```csharp
var normalized = NormalizeOrder(order); // updates order in the database
var total = CalculateTotal(normalized); // calls a tax API
var label = FormatTotal(total);         // reads CurrentCulture
```

The code may still be valid, but the caller contract is larger. Mistaking an impure call for a pure one can break behavior because the caller may retry, cache, parallelize, or reorder it under assumptions that are false. The opposite mistake is usually safer, but it costs flexibility. The method becomes harder to move, cache, test, or reuse because the caller is being conservative.

In procedural code, that uncertainty often turns into manual orchestration:

```csharp
// Treat each call as potentially effectful.
// Call once, store the result, preserve order, and avoid hidden retries.
var normalized = NormalizeOrder(order);
var total = CalculateTotal(normalized);
var label = FormatTotal(total);

SaveReceipt(order.Id, label);
```

There is nothing wrong with that shape. Many application services should look like that. It is often a strength of procedural code: the sequence is visible, the effect boundaries are visible, and the caller is preserving them on purpose.

With pure calculations, some of that burden disappears:

```csharp
var total = CalculateTotal(normalized, taxRate, discount);
var label = FormatTotal(total, culture);

var preview = FormatTotal(
    CalculateTotal(normalized, taxRate, discount),
    culture);
```

That refactor may duplicate work, but it does not duplicate an external effect. The calculation can be moved, repeated, cached, or inlined with fewer behavioral concerns.

## Types for values, purity for calls

Programs make value assumptions whether or not the type system records them. Static types move more of them into declarations the compiler can check. Purity does something similar for calls.

Code reviews often use phrases like "this is just a calculation" or "this leaves objects unchanged." Those phrases name behavioral contracts. If purity is only a guess, the programmer has to carry that contract manually.

The useful engineering promise is narrow: the call behaves like a calculation.

That promise composes in a predictable way. Pure code built from pure code stays pure. One effectful step changes the contract of the whole method. That is all I mean by saying impurity propagates from the caller's point of view. Nothing moral is happening. The caller contract simply gets larger unless the effect is fully encapsulated behind the same outward behavior. Once a calculation reads the clock, writes a file, calls a service, mutates shared state, or invokes an effectful callback, callers must account for that larger behavior.

## Loops and reuse

The same distinction shows up in ordinary loops.

```csharp
var labels = new List<string>();

foreach (var order in orders)
{
    var total = CalculateTotal(order, taxRate, discount);
    labels.Add(FormatTotal(total, culture));
}
```

If `CalculateTotal` and `FormatTotal` are pure, the calculation inside the loop is mostly about values. The caller can rerun it while debugging, split it into batches, cache intermediate results, or parallelize the calculation itself without changing what each call means. The surrounding `labels.Add(...)` is still ordinary mutable orchestration, so parallelizing the whole loop would require a different collection strategy or a deterministic gather step. That is also why pure calculations are easy to run concurrently: without shared mutable state, callers do not need synchronization to preserve the calculation's semantics.

Now change the contract behind the same names:

```csharp
var labels = new List<string>();

foreach (var order in orders)
{
    var total = CalculateTotal(order); // calls a tax API
    labels.Add(FormatTotal(total));    // reads CurrentCulture
}
```

The loop still looks ordinary, but the call pattern matters much more now. How many times does the loop run? What happens if processing restarts halfway through? Is it safe to enumerate `orders` twice? Can the work move across threads? Can the result be cached and reused tomorrow? Those questions matter because the methods are no longer just calculations.

The visible shapes may look like this:

```text
Order -> Money
Money -> string
```

The real shapes are closer to this:

```text
Order + tax service + current policy -> Money
Money + current culture -> string
```

The same thing happens in loops. The loop is not harder because `foreach` is special. It is harder because every extra call site inherits the larger contract.

## Number, timing, and order

Purity relaxes constraints on number, timing, and order. For a pure method, calling it twice usually changes performance more than program meaning. For an effectful method, number, timing, and order may be part of the contract. In many systems, that visible warning label is enough because the caller only needs "run this once, here, in order."

Behavioral safety is not the same as zero cost. Repeating a pure call still burns CPU, allocates memory, and may create garbage-collection pressure. Memoization can trade memory for work, but it is still a trade. Purity buys safety around behavior, not free execution.

Retry logic makes this concrete:

```csharp
var total = Retry(
    () => CalculateTotal(order, taxRate, discount),
    attempts: 3);

var invoice = Retry(
    () => CreateInvoice(order),
    attempts: 3);
```

Both calls can fit behind a `Func<T>`. The type leaves open the important question:

```text
Is this operation safe to repeat?
```

If `CalculateTotal` is a pure calculation, repeating it does not send another email, write another row, publish another event, or mutate caller-owned state. Retrying may still be useless if the failure is deterministic, but the repeat itself is harmless outside the process. That is not idempotence; it is repeatable evaluation with no extra external effect. A pure function can still be non-idempotent: `x => x + 1` is pure, but applying it twice is not the same as applying it once.

`CreateInvoice` is different. It may allocate an invoice number, read the current time, persist a row, send a message, or publish an event. Repeat it and you may create two invoices.

`CreateInvoice` can still be a good boundary. The caller just needs a different contract. A payment operation can be safe to retry when it uses an idempotency key and the receiving system honors it. The operation remains effectful. Here "idempotent" is the distributed-systems sense: repeating the same logical request produces the same external state. The idempotency key creates a contract like this:

```text
This operation touches the world, and repeating the same logical request is safe.
```

That is a useful pattern. It gives an effectful call one pure-like property: repetition becomes safer. The caller gains flexibility even though the call still interacts with the world.

## Mutation and hidden inputs

Purity does not forbid local mutation.

This can still be pure:

```csharp
public static ImmutableList<Item> AddItem(
    ImmutableList<Item> items,
    Item item)
{
    var builder = items.ToBuilder();
    builder.Add(item);
    return builder.ToImmutable();
}
```

The function mutates `builder`, but that mutation is local and the returned result is immutable. Assuming `Item` is itself treated as an immutable value, the caller cannot observe the intermediate mutation.

It is still not free. Purity removes one class of semantic problems, not time and memory costs. Immutable and persistent collections can reduce copying through structural sharing, but the cost model is still part of the design.

This is different:

```csharp
public static void AddItem(List<Item> items, Item item)
{
    items.Add(item);
}
```

That mutates caller-owned state. The caller observes the change through the same list reference. That is an externally visible effect.

What matters is not mutation in the abstract, but hidden inputs and externally visible effects.

Hidden inputs follow the same pattern:

```csharp
string FormatAmount(decimal amount)
{
    return string.Format("{0:C}", amount);
}

bool IsExpired(Subscription subscription)
{
    return subscription.ExpiresAt < DateTimeOffset.UtcNow;
}
```

The visible shapes look like `decimal -> string` and `Subscription -> bool`. The real shapes are closer to `decimal + current culture -> string` and `Subscription + current time -> bool`. At some boundaries, `CurrentCulture`, `UtcNow`, or `Guid.NewGuid()` are exactly the right choice. The distinction matters when the caller needs repeatability, preview, replay, comparison, or a stable cache key.

## Boundaries and restraint

Method signatures are useful. In C#-style code, they tell us parameter types, return types, and awaitable shapes. They usually leave out whether a method reads the clock, depends on `CurrentCulture`, calls a database, writes a file, or mutates shared state. That does not mean every dependency should become a parameter. Effects belong where callers expect interaction with the world.

Repositories should talk to databases. Controllers should orchestrate. Job handlers should sequence effects. Migration scripts should update state. In code like that, a procedural style is often the most honest representation of the work. Forcing every such boundary through tiny pure wrappers can make the code less clear.

Functional core / imperative shell is one way to apply this idea. Gary Bernhardt popularized that phrasing. The shell gathers facts from the world and performs visible effects. The core takes explicit values and returns a calculation, decision, or plan. Part of the appeal is testing: a pure core is usually testable without mock-heavy harnesses, while the shell stays thin and generic.

```text
Use dependency injection at interaction boundaries.
Use explicit values in calculation-heavy code.
```

Constructor injection is appropriate for application services, repositories, adapters, clients, and orchestration code. Explicit method parameters are often better for domain policy, pricing, validation, authorization, scheduling, retry rules, and other code where the main job is to decide. This is not "procedural versus functional." Procedural code is often best for sequencing interactions. Pure calculations are often best for reusable logic where callers benefit from stronger assumptions. The point is to put each style where its contract matches the job.

Some languages and tools track purity or effects directly. In many mainstream procedural and object-oriented languages, purity rarely appears in the signature, so we express it indirectly through naming, documentation, boundaries, tests, code review, and analyzers.

That is still useful. A static analyzer, language feature, or project convention that marks a calculation as pure can solidify assumptions that were otherwise informal. It can catch accidental reads of time, culture, global state, random values, files, databases, or other services. It does not need to prove everything. It only needs to make an important assumption visible enough to review.

There is a tradeoff. Making behavior visible can make code more verbose. Passing `now`, `culture`, `taxRate`, or `discount` explicitly can be overkill. Expose the dependencies that materially affect correctness, repeatability, reuse, or caller obligations.

There is also a bad version of this idea:

```csharp
var a = Step1(input);
var b = Step2(a);
var c = Step3(b);
var d = Step4(c);
```

The shape itself is not the problem. Passing the output of one pure function into the next is exactly how composition is supposed to work. The problem is the names. `CalculateTotal`, `DecideRenewal`, `ValidatePolicy`, and `PlanShipment` are useful boundaries. `Step1` through `Step4` usually tell the reader nothing.

Pure and effectful methods make different promises. Both are useful, and both belong in real programs. The goal is not to eliminate side effects. The goal is to isolate and manage them so fewer method calls become surprising.
