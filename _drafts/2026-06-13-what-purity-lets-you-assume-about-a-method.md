---
title: "What Purity Lets You Assume About a Method"
date: 2026-06-13
description: "Types make assumptions about values explicit. Purity does something similar for method calls."
---

A caller always assumes something. If I call `DeleteCustomer(...)`, I assume it deletes. If I call `TryParse(...)`, I assume ordinary failure is reported through the return value. If I call `GetUserAsync(...)`, I assume I have awaitable work. If I call `CalculateTotal(...)`, I assume I have a calculation. Names, types, documentation, conventions, and tooling tell me what kind of call I am dealing with.

One contract signatures often omit is whether a call is value-like or interaction-like. The examples use C#-style syntax, but the point is broader. In many imperative and object-oriented languages, effects are ordinary and purity is usually a convention rather than a checked feature.

This is not an argument that ordinary procedural code is broken. A lot of it is direct and truthful: read input, do work, write output, return. In that style, order is visible, effects are the point, and naming plus layering often carry enough signal. Purity matters most in methods callers want to treat like calculations.

By "impurity," I mean the call depends on more than its explicit inputs or produces more than its returned value. That includes visible effects like writing a file, calling a service, sending an email, logging, or mutating caller-owned state. It also includes hidden inputs like reading the clock, using randomness, current culture, or global configuration. In both cases, the caller is depending on context absent from the parameter list. In small code, convention is often enough. In larger programs, it gets expensive.

That leads to the core claim: types make assumptions about values explicit. Purity does something similar for calls. A pure call is value-like. Its observable behavior is determined by its explicit inputs, and externally visible effects are absent.

That contract makes some caller transformations less dangerous: repeat the call, retry it, cache it, reorder it, parallelize it, or compose it with other calculations. It does not make every transformation cheap or useful, but it does make more of them semantically safe by default. Effects are necessary, though. A useful program eventually sends the email, writes the row, reads the clock, calls the API, and mutates state. Effectful calls need a different contract. They may still be safe to retry, cache, parallelize, or reorder, but some other property has to make that true: idempotency, retry-safety, cache-safety, thread-safety, transactionality, or an explicit effect boundary. The practical question is simple: what can the caller safely do with this method call?

## When The Assumption Matters

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

## Types For Values, Purity For Calls

Programs make value assumptions whether or not the type system records them. Static types move more of them into declarations the compiler can check. If every value were just `byte[]`, those assumptions would still exist. They would move into comments, casts, helper functions, runtime checks, and programmer memory. Purity does something similar for calls.

When I retry a method, cache its result, call it twice, use it in a loop, run it in parallel, or move it earlier in the program, I am assuming something about the method's behavior. The code may use phrases like "this is just a calculation," "this is safe to retry," "this helper only checks a condition," or "this leaves objects unchanged." Those phrases still name behavioral contracts. If purity is only a guess, the programmer has to carry that assumption manually. In a small script, that may be fine. In a larger program, it is easier to lose track of which calls are calculations and which calls touch the world.

By "pure" here, I mean the practical code-review version: all inputs are explicit, the same explicit inputs produce the same observable behavior, and there are no externally visible effects. Totality is a separate contract. So are performance, thread safety, naming, stable equality, and ease of use. The useful engineering promise is narrower: the call behaves like a calculation.

That promise composes in a predictable way. Pure code built from pure code stays pure. One effectful step changes the contract of the whole method. That is all I mean by saying impurity propagates. Nothing moral is happening. The caller contract simply gets larger. Once a calculation reads the clock, writes a file, calls a service, mutates shared state, or invokes an effectful callback, callers must account for that larger behavior.

## Loops And Reuse

The same distinction shows up in ordinary loops.

```csharp
var labels = new List<string>();

foreach (var order in orders)
{
    var total = CalculateTotal(order, taxRate, discount);
    labels.Add(FormatTotal(total, culture));
}
```

If `CalculateTotal` and `FormatTotal` are pure, this loop is mostly about values. The caller can rerun it while debugging, split it into batches, cache intermediate results, or parallelize parts of it without changing what each call means.

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

## Number, Timing, And Order

Purity relaxes constraints on number, timing, and order. For a pure method, calling it twice usually changes performance more than program meaning. For an effectful method, number, timing, and order may be part of the contract. In many systems, that visible warning label is enough because the caller only needs "run this once, here, in order."

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

If `CalculateTotal` is a pure calculation, repeating it has the same external footprint as calling it once. Retrying may still be useless if the failure is deterministic, but the repeat itself is harmless outside the process.

`CreateInvoice` is different. It may allocate an invoice number, read the current time, persist a row, send a message, or publish an event. Repeat it and you may create two invoices.

`CreateInvoice` can still be a good boundary. The caller just needs a different contract. A payment operation can be safe to retry when it uses an idempotency key and the receiving system honors it. The operation remains effectful. The idempotency key creates a contract like this:

```text
This operation touches the world, and repeating the same logical request is safe.
```

That is a useful pattern. It gives an effectful call one pure-like property: repetition becomes safer. The caller gains flexibility even though the call still interacts with the world.

## Mutation And Hidden Inputs

Purity does not forbid local mutation.

This can still be pure:

```csharp
public static IReadOnlyList<Item> AddItem(
    IReadOnlyList<Item> items,
    Item item)
{
    var copy = items.ToList();
    copy.Add(item);
    return copy;
}
```

The function mutates `copy`, but `copy` is local and the caller cannot observe the intermediate mutation.

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

## Boundaries And Restraint

Method signatures are useful. In C#-style code, they tell us parameter types, return types, and awaitable shapes. They usually leave out whether a method reads the clock, depends on `CurrentCulture`, calls a database, writes a file, or mutates shared state. That does not mean every dependency should become a parameter. Effects belong where callers expect interaction with the world.

Repositories should talk to databases. Controllers should orchestrate. Job handlers should sequence effects. Migration scripts should update state. In code like that, a procedural style is often the most honest representation of the work. Forcing every such boundary through tiny pure wrappers can make the code less clear.

Functional core / imperative shell is one way to apply this idea. The shell gathers facts from the world and performs visible effects. The core takes explicit values and returns a calculation, decision, or plan.

```text
Use dependency injection in the shell.
Use explicit values in the core.
```

Constructor injection is appropriate for application services, repositories, adapters, clients, and orchestration code. Explicit method parameters are often better for domain policy, pricing, validation, authorization, scheduling, retry rules, and other code where the main job is to decide. This is not "procedural versus functional." Procedural code is often best for sequencing interactions. Pure calculations are often best for reusable logic where callers benefit from stronger assumptions. The point is to put each style where its contract matches the job.

Some languages and tools track purity or effects directly. In many mainstream procedural and object-oriented languages, purity rarely appears in the type, so we express it indirectly through naming, documentation, boundaries, tests, code review, and analyzers. That is still useful. A static analyzer, language feature, or project convention that marks a calculation as pure can solidify assumptions that were otherwise informal. It can catch accidental reads of time, culture, global state, random values, files, databases, or other services. It does not need to prove everything. It only needs to make an important assumption visible enough to review.

There is a tradeoff. Making behavior visible can make code more verbose. Passing `now`, `culture`, `taxRate`, or `discount` explicitly can be overkill. Expose the dependencies that materially affect correctness, repeatability, reuse, or caller obligations.

There is also a bad version of this idea:

```csharp
var a = Step1(input);
var b = Step2(a);
var c = Step3(b);
var d = Step4(c);
```

Purity alone is insufficient. A pure function should still earn its name. `CalculateTotal`, `DecideRenewal`, `ValidatePolicy`, and `PlanShipment` are useful boundaries. `Step1` through `Step4` usually are filler.

Pure and effectful methods make different promises. Both are useful, and they preserve different caller assumptions. The goal is fewer surprising method calls.
