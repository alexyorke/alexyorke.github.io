---
title: "What Purity Lets a Caller Assume"
date: 2026-06-13
description: "Types make assumptions about values explicit. Purity does something similar for method calls."
---

A program is a sequence of steps. If a method call is one of those steps, the caller needs to know what kind of step it is before placing it in a larger sequence.

Some methods are mostly calculations. Others interact with the world. A method might compute a total, format a string, or validate an order. Another might write a row, send an email, read the clock, mutate shared state, or hit the network. By "effect" here, I mean that second category: behavior beyond the returned value that depends on or changes the surrounding world.

We already rely on this distinction even when we do not name it. We treat `items.Count`, `string.Concat(a, b)`, and `CalculateSubtotal(lines)` as calls we can repeat, cache, or move around without changing the rest of the program. We treat `LoadCustomer(id)`, `SaveOrder(order)`, and `SendEmail()` differently because number, timing, and order may matter.

That is why purity is useful as a caller contract. Types make assumptions about values explicit. Purity does something similar for calls. It tells the caller which operations are safe around the call: repeat it, duplicate it, cache it, reorder it, parallelize it, or compose it with other calculations.

The more assumptions a caller can make safely, the easier a method is to move, reuse, and combine with other code. The more a method depends on ambient setup, the more every caller has to reconstruct that setup or trust that someone else already did.

Effectful code can regain some of those freedoms, but usually only with more structure around it. Idempotency keys, transactions, snapshots, explicit context objects, queues, and carefully managed retries can make an effectful operation safer to repeat or move. Those are good tools. They are also extra contract surface. When the supporting conditions stay ambient instead of explicit, the caller often has to trust that the surrounding system was set up correctly.

If that contract is wrong, the caller can make bad moves. Retry a method that quietly sends email and you may send two messages. Cache a method that quietly reads the clock and you may freeze the wrong value. Treat every call as though it might touch the world and ordinary composition becomes overly conservative.

That is the part of a method contract I care about here. This is close to command-query separation, but the emphasis is a little different: I am asking what guarantees the caller gets when a call behaves like a calculation. The examples use C#-style syntax, but the point is broader. This is not an argument that ordinary procedural code is broken. Many steps in a real program are supposed to interact with the world.

By "pure," I mean a call that behaves like a calculation: when it returns normally, the same explicit inputs produce the same returned value, and the call leaves no externally visible effects behind. For an instance method, the receiver's observable state is part of that story too. By "impure," I mean a call depends on more than its explicit inputs or produces more than its returned value. That includes reading time or culture, using global configuration, mutating caller-visible state, writing a file, or sending an email. Here, "observable" means behavior that callers, tests, users, operators, or other systems may reasonably depend on.

A pure call is easier to repeat, duplicate, cache, reorder, parallelize, or compose with other calculations. In languages with observable reference identity, such as C#, that still assumes the result is being treated as a value. The practical question is simple: what can the caller safely do with this method call?

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

Programs make value assumptions whether or not the type system records them. Static types move more of them into declarations the compiler can check. Purity plays a similar role for calls.

At the lowest level, a program can treat data as raw bytes or memory and still work. The assumptions do not disappear. The code still has to know whether that data is meant to be a string, a number, an image, or something else, and which operations make sense for it. Types make those assumptions easier to check and easier to share. Once a value is known to be a `string`, other code can safely use string operations on it. Once a value is known to be a `Money`, callers and libraries can define operations that are sensible for money and reject ones that are not.

Code reviews often use phrases like "this is just a calculation" or "this leaves objects unchanged." Those phrases name behavioral contracts. If purity is only a guess, the programmer has to carry that contract manually.

The same thing happens with calls. If a method is known to behave like a calculation, other code can use it under stronger assumptions. It can be passed into a sort comparison, used inside a loop, cached behind a memoizer, retried without duplicating an external effect, or composed into larger calculations with less defensive setup. If that property is only informal, every caller has to rediscover it or trust it.

None of this requires a special framework. In C#-style code, a pure method is still just an ordinary method whose behavior is narrow enough that callers can safely treat it like a calculation.

The useful engineering promise is narrow: the call behaves like a calculation.

That promise composes in a predictable way. Pure code built from pure code stays pure. One effectful step changes the contract of the whole method. That is all I mean by saying impurity propagates from the caller's point of view. Nothing moral is happening. The caller contract simply gets larger unless the effect is fully encapsulated behind the same outward behavior. Once a calculation reads the clock, writes a file, calls a service, mutates shared state, or invokes an effectful callback, callers must account for that larger behavior.

## Loops, callbacks, and reuse

The same distinction shows up in ordinary loops and in library code that calls your logic for you.

When you write procedural code directly, you often control the order of steps yourself. You know where the loop starts, where it ends, and where each effect happens. Once you pass behavior into a library method, you usually give up some of that control. The library may call your code zero times, once, many times, in a different order than you expected, or under an implementation strategy that changes later.

Sorting is a simple example:

```csharp
orders.Sort((left, right) =>
    left.Total.CompareTo(right.Total));
```

This does not require full philosophical purity, but it does require the comparison to behave like a calculation for ordering purposes. Once the sort owns the call pattern, the comparison needs to give consistent answers for the same inputs. If the comparison reads the clock, consults mutable global state, or changes shared state that later comparisons depend on, the sort becomes harder to reason about because algorithm details become observable.

Even harmless-looking side effects can matter here. Logging from inside the comparison may be acceptable, but it still makes call count and call order observable. The sort can only stay an interchangeable library operation if callers are willing to treat those details as irrelevant.

The same pressure appears with predicates, selectors, and other callbacks. The more the callback behaves like a calculation, the less the surrounding framework has to care about when, how often, or in what order it runs.

The same distinction also shows up in ordinary loops.

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

The same thing happens in loops. The loop is not harder because `foreach` is special. It is harder because every extra call site inherits the larger contract. The difference is that in a loop you usually own the call pattern yourself. With callbacks handed to library code, someone else owns it.

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

The same thing happens with other guarantees. A stable cache around an effectful call may depend on a version key, a snapshot, a clock boundary, or a rule that the underlying data cannot change during the operation. A retry may depend on deduplication state in another system. A deterministic result may depend on reading the time once at the boundary and passing it inward. None of that is fake or bad. It just means the property is no longer coming from the method alone. It is coming from the method plus supporting infrastructure.

In that sense, effectful systems often try to recover some of the caller freedoms that pure methods provide directly. They pin down hidden inputs, suppress duplicate effects, or hold the environment steady enough that the call behaves more predictably. That is often the right engineering move. It is still a larger maintenance burden because part of the contract now lives outside the method.

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

A content hash is another good example:

```csharp
string ComputeDigest(byte[] payload)
{
    return Convert.ToHexString(SHA256.HashData(payload));
}
```

That kind of method is useful precisely because callers can treat it like a calculation. If the same payload could produce a different digest because of hidden state, then deduplication, cache keys, and change detection would all get harder to trust. This is one place where "same input, same output" is not an academic preference. It is part of why the method is useful at all.

One common response is to hold those hidden inputs steady from the outside: freeze the clock for a test, fix the culture for a request, snapshot the database, or thread a request context through the call chain. That can be the correct solution. It also shows the underlying pressure. As soon as the caller needs predictable behavior, it starts trying to make those hidden inputs explicit or fixed.

Containers and similar environment controls fit the same pattern. Pinning the OS image, locale, configuration, and toolchain can make a program more reproducible by narrowing ambient variation. That is often worthwhile. It still does not make an effectful call pure. It makes some hidden inputs more stable.

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

That is also why reducing hidden inputs matters. The more behavior depends on ambient setup, the more the caller has to trust that time, culture, feature flags, caches, retries, and external state all line up the same way every time. Real programs need some of that machinery. Keeping more of the important logic in pure calculations shrinks the amount of machinery the caller must trust and makes the remaining logic easier to move and reuse without rebuilding the same setup everywhere.

There is also a bad version of this idea:

```csharp
var a = Step1(input);
var b = Step2(a);
var c = Step3(b);
var d = Step4(c);
```

The shape itself is not the problem. Passing the output of one pure function into the next is exactly how composition is supposed to work. The problem is the names. `CalculateTotal`, `DecideRenewal`, `ValidatePolicy`, and `PlanShipment` are useful boundaries. `Step1` through `Step4` usually tell the reader nothing.

Pure and effectful methods make different promises. Both are useful, and both belong in real programs. The goal is not to eliminate side effects. The goal is to isolate and manage them so fewer method calls become surprising.
