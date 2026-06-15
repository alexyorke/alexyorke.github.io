---
title: "What Purity Lets You Assume About a Method"
date: 2026-06-13
description: "Types make assumptions about values explicit; a purity contract makes assumptions about method calls explicit."
---

A caller always assumes something.

If I call `DeleteCustomer(...)`, I assume it deletes. If I call `TryParse(...)`, I assume ordinary failure is reported through the return value. If I call `GetUserAsync(...)`, I assume I have awaitable work. If I call `CalculateTotal(...)`, I assume I have a calculation.

Names, types, documentation, conventions, and tooling all help tell me what kind of call I am dealing with.

This article is about one contract that is often missing from the signature: whether a call is value-like or interaction-like.

The examples use C#-style syntax because that is the code I usually write. The point applies more broadly to mainstream imperative and object-oriented languages where effects are ordinary and purity is usually a convention rather than a checked language feature.

By "effect," I mean behavior that reaches beyond the returned value. That includes writing a file, calling a service, sending an email, logging, mutating caller-owned or shared state, reading the clock, using randomness, reading current culture, or depending on global configuration. Some of those are outputs into the world. Some are hidden inputs from the world. Either way, the call is interacting with context the caller cannot see in the parameter list.

At a call site, one of three things is happening: I know the call is pure, I know the call is effectful, or I am guessing. The last case is where large programs get expensive.

The thesis is:

```text
Types make assumptions about values explicit.
A purity contract makes assumptions about calls explicit.
```

Purity says that a call is value-like. Its observable behavior is determined by its explicit inputs, and externally visible effects are absent.

That contract makes more caller transformations valid by default:

```text
repeat
retry
cache
reorder
replay
parallelize
compose
```

Effects are necessary. A useful program eventually sends the email, writes the row, reads the clock, calls the API, and mutates state. Effectful calls need a different contract. They may still be safe to retry, cache, parallelize, or reorder, but some other property has to make that true: idempotency, retry-safety, cache-safety, thread-safety, transactionality, or an explicit effect boundary.

Purity has been discussed for a long time in functional programming, programming-language theory, and UI systems that keep rendering deterministic. I am using it here for a smaller programming question:

```text
What can the caller safely do with this method call?
```

## When The Assumption Matters

Imagine this code:

```csharp
var normalized = NormalizeOrder(order);
var total = CalculateTotal(normalized);
var label = FormatTotal(total);
```

Most of the time, informal evidence is enough. I infer a contract from names, location, and convention. `NormalizeOrder`, `CalculateTotal`, and `FormatTotal` look like calculations.

If that inference is correct, the code is easy to work with. I can call `CalculateTotal` twice while debugging. I can cache `FormatTotal`. I can replay the whole sequence with recorded inputs. I can move the calculation into a test, a dry-run path, or a background validation job.

The caller has flexibility because the calls are value-like.

Now change the contract behind the same names:

```csharp
var normalized = NormalizeOrder(order); // updates order in the database
var total = CalculateTotal(normalized); // calls a tax API
var label = FormatTotal(total);         // reads CurrentCulture
```

The code may still be valid. The names may even make sense in the application where they live. The caller contract is larger, though.

Now the caller has to ask:

```text
Can I call this twice?
Can I call it in a loop?
Can I move it earlier?
Can I run it in parallel?
Can I cache the result?
Can I replay it from production inputs?
Can I call it in a preview path?
```

Those questions are not abstract. Calling a function twice might send two HTTP requests, insert two rows, produce two invoice numbers, or log two audit records. Moving a call earlier might read a different clock value. Running calls in parallel might race on shared state.

The problem is contract mismatch. Treating an effectful call as pure is dangerous because the caller may retry, cache, parallelize, or reorder it under assumptions that are false. Treating a pure call as effectful is usually safer, but it gives up useful flexibility. The method becomes harder to move, cache, test, or reuse because the caller is being conservative.

In procedural code, that uncertainty often turns into manual orchestration:

```csharp
// Treat each call as potentially effectful.
// Call once, store the result, preserve order, and avoid hidden retries.
var normalized = NormalizeOrder(order);
var total = CalculateTotal(normalized);
var label = FormatTotal(total);

SaveReceipt(order.Id, label);
```

There is nothing wrong with that shape. Many application services should look like that. The point is that the caller is now responsible for preserving the sequence and avoiding extra calls.

With pure calculations, some of that burden disappears:

```csharp
var total = CalculateTotal(normalized, taxRate, discount);
var label = FormatTotal(total, culture);

var preview = FormatTotal(
    CalculateTotal(normalized, taxRate, discount),
    culture);
```

That refactor may duplicate work, but it does not duplicate an external effect. The calculation can be moved, repeated, cached, or inlined more freely.

This is the practical value of knowing whether a method is pure. It tells the caller which constraints have been relaxed.

## Types For Values, Purity For Calls

Static types make some assumptions about values visible.

A dynamically typed program still has value assumptions. If I add two values, call `.Length`, index into a collection, or pass a value to a method, I am assuming those values support those operations.

Static types move some of those assumptions into declarations the compiler can check.

At the extreme, imagine every value was just a blob of bytes:

```csharp
byte[] value = LoadValue();
```

Sometimes bytes are exactly what you want. If you are writing a file or sending a packet, bytes may be the right abstraction.

For ordinary application code, though, the program still has assumptions:

```text
Is this an image?
Is this a number?
Is this text?
Is this a serialized customer?
Can I add it?
Can I index into it?
Can I format it?
```

Those assumptions do not disappear. They move into comments, conventions, casts, helper functions, runtime checks, and programmer memory. Types reduce that overhead by restricting which operations are available on which values.

Purity plays a similar role for calls.

When I retry a method, cache its result, call it twice, pass it to LINQ, run it in parallel, or move it earlier in the program, I am assuming something about the method's behavior. The code may use phrases like "this is just a calculation," "this is safe to retry," "this leaves objects unchanged," or "this predicate only checks a condition." Those phrases still name behavioral contracts.

If purity is only a guess, the programmer has to carry that assumption manually. In a small script, that may be fine. In a larger program, it is easy to lose track of which calls are calculations and which calls interact with the world.

By "pure" here, I mean the practical code-review version:

```text
all inputs explicit
deterministic observable outcome out
externally visible effects absent
```

The outcome may be a returned value or a deterministic failure. Totality is a separate contract. So are performance, thread safety, naming, stable equality, and ease of use.

The useful engineering promise is narrower:

```text
the call behaves like a calculation
```

That promise composes in a predictable way:

```text
pure + pure = pure
pure + effectful = effectful
effectful + effectful = effectful
```

This is the practical sense in which effects "contaminate" a call. Nothing moral is happening. The caller contract simply gets larger. Once a calculation reads the clock, writes a file, calls a service, mutates shared state, or invokes an effectful callback, callers need to account for that larger behavior.

The upside is that pure composition preserves the smaller contract. A larger calculation built from smaller pure calculations is still a calculation. One effectful step changes the contract of the whole method.

That is why it can be useful to keep pure code near other pure code. Useful calculation boundaries stay small, stable, and easy to move.

## Number, Timing, And Order

Purity relaxes constraints on number, timing, and order.

For a pure method, calling it twice usually changes performance more than program meaning. Calling it now or later usually produces the same observable outcome. Reordering it with another pure calculation is usually safe, aside from cost or deterministic failure.

For an effectful method, number, timing, and order may be the contract.

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

`CreateInvoice` is different. It may allocate an invoice number, read the current time, persist a row, send a message, or publish an event. Repeating it may create two invoices.

`CreateInvoice` can still be a good boundary. The caller needs a different contract.

A payment operation can be safe to retry when it uses an idempotency key and the receiving system honors that key. The operation remains effectful. The idempotency key creates a contract like this:

```text
This operation touches the world, and repeating the same logical request is safe.
```

That is a useful pattern. It gives an effectful call some pure-like properties. Repetition becomes safer. The caller has more flexibility. Another design has rebuilt part of the purity contract around an interaction with the world.

## Higher-Order Functions

The propagation problem is clearest with higher-order functions.

```csharp
public static IEnumerable<Order> MatchingOrders(
    IReadOnlyList<Order> orders,
    Func<Order, bool> predicate)
{
    return orders.Where(predicate);
}
```

Assume the source collection is already materialized and stable. The source still has its own contract, but this example focuses on the predicate.

If `predicate` is pure, `MatchingOrders` is mostly about values. The predicate is just:

```text
Order -> bool
```

With an effectful predicate, traversal details become caller-relevant. Logging, mutating state, reading the clock, calling a service, or sending telemetry all make the call pattern visible.

```csharp
var matching = MatchingOrders(orders, order =>
{
    _audit.Record("Checked " + order.Id);
    return order.Total > 500;
});
```

Now the caller may need to ask whether the sequence is lazy, how many times the predicate runs, what order it runs in, what happens if the result is enumerated twice, and whether a future implementation could change traversal strategy or run in parallel.

Those questions fade into the background when the predicate is pure. They become central when the predicate has effects.

The type says `Func<Order, bool>`, and two very different contracts can hide behind that shape:

```text
Order -> bool
Order + hidden world state -> bool + hidden effects
```

C# and many similar languages leave those contracts indistinguished at the type level.

This shows up in ordinary library design too. A comparer passed to sorting code is expected to behave consistently. A hash function used by a dictionary is expected to be stable for the key while it is in the dictionary. Those assumptions can exist even when the word "pure" is absent.

## Mutation And Hidden Inputs

Purity allows some local mutation.

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

The function mutates `copy`, but `copy` is local. The caller cannot observe the intermediate mutation. For the same `items` and `item`, the observable result is the same.

This is different:

```csharp
public static void AddItem(List<Item> items, Item item)
{
    items.Add(item);
}
```

That mutates caller-owned state. The caller observes the change through the same list reference. That is an externally visible effect.

So the useful distinction is hidden inputs and externally visible effects.

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

The visible shapes look like `decimal -> string` and `Subscription -> bool`. The real shapes are closer to `decimal + current culture -> string` and `Subscription + current time -> bool`.

At some boundaries, `CurrentCulture`, `UtcNow`, or `Guid.NewGuid()` are exactly the right choice. The distinction matters when the caller needs repeatability, preview, replay, comparison, or a stable cache key.

## Boundaries And Restraint

Method signatures are useful. In C#-style code, they tell us parameter types, return types, and awaitable shapes. Nullable reference type annotations can also make some assumptions visible enough for warnings and review.

They usually leave out whether a method reads the clock, depends on `CurrentCulture`, calls a database, writes a file, mutates shared state, or leaves some other observable effect behind.

That does not mean every dependency should become a parameter.

Effects belong in programs. They belong in the parts of the program where the caller expects interaction with the world.

This is where functional core / imperative shell helps. The shell gathers facts from the world and performs visible effects. The core takes explicit values and returns a calculation, decision, or plan.

```text
Use dependency injection in the shell.
Use explicit values in the core.
```

Constructor injection is appropriate for application services, repositories, adapters, clients, and orchestration code. Explicit method parameters are often better for domain policy, pricing, validation, authorization, scheduling, retry rules, and other code where the main job is to decide.

Some languages and tools track purity or effects directly. That gives stronger guarantees. In many procedural and object-oriented languages, purity rarely appears in the type, so we express it indirectly through naming, documentation, boundaries, tests, code review, and analyzers.

That is still useful. A static analyzer, language feature, or project convention that marks a calculation as pure can solidify assumptions that were otherwise informal. It can help catch accidental reads of time, culture, global state, random values, files, databases, or other services.

The strongest version is language-enforced. The next best version is tool-enforced. A convention is still useful, but it asks every reader to remember the rule.

The tool does not need to prove everything to be valuable. It only needs to make an important assumption visible enough to review.

There is a tradeoff. Making behavior visible can make code more verbose. Passing `now`, `culture`, `taxRate`, or `discount` explicitly can be overkill. Expose the dependencies that materially affect correctness, repeatability, reuse, or caller obligations.

The bad version of this idea is easy to write:

```csharp
var a = Step1(input);
var b = Step2(a);
var c = Step3(b);
var d = Step4(c);
```

Purity alone is insufficient. A pure function should still earn its name. `CalculateTotal`, `DecideRenewal`, `ValidatePolicy`, and `PlanShipment` are useful boundaries. `Step1` through `Step4` usually are filler.

Purity does not require adopting functional programming, using monads, or throwing out procedural code. You can use pure functions as ordinary calculation boundaries inside code that is otherwise imperative.

Pure methods and effectful methods make different promises. Pure methods are value-like. Effectful methods are interaction-like. Both are useful, and they preserve different caller assumptions.

The goal is fewer surprising method calls.
