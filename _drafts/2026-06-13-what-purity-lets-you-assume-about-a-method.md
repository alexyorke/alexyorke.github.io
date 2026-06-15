---
title: "What Purity Lets You Assume About a Method"
date: 2026-06-13
description: "Types make assumptions about values explicit; a purity contract makes assumptions about method calls explicit."
---

A caller always assumes something.

Every method call depends on some behavioral contract.

`DeleteCustomer(...)` is assumed to delete. `TryParse(...)` is assumed to report ordinary failure through its return value. `GetUserAsync(...)` is assumed to produce awaitable work. `CalculateTotal(...)` is assumed to calculate a total.

If every method had to be treated as a mystery, ordinary APIs would become unusable. A method named `Sort` could delete files. A method named `FormatAmount` could send email. A predicate passed to `Where` could mutate the database.

In practice, we rely on names, types, documentation, conventions, and tooling to tell us what kind of behavior we are dealing with.

This post is about one contract that is often absent from the signature: whether a method call is value-like or interaction-like.

The examples use C#-style syntax because that is the code I usually write. The point applies more broadly to mainstream imperative and object-oriented languages where effects are ordinary and purity is usually a convention rather than a checked language feature.

The thesis is:

```text
Types make assumptions about values explicit.
A purity contract makes assumptions about calls explicit.
```

Purity says a call is value-like. Its observable behavior is determined by its explicit inputs, and externally visible effects are absent.

That contract makes more caller transformations valid by default: repeat, retry, cache, reorder, replay, parallelize, and compose.

Effects are necessary. A useful program eventually sends the email, writes the row, reads the clock, calls the API, and mutates state. Effectful calls need a different contract. They may still be safe to retry, cache, parallelize, or reorder when another property makes that true: idempotency, retry-safety, cache-safety, thread-safety, transactionality, or an explicit effect boundary.

Correctness depends on that contract. A method that looks like a calculation and behaves like an interaction is harder to retry, cache, move, test, and refactor safely.

Another way to say it:

```text
Purity usually makes the number, timing, and order of calls less important.
Effects can make them part of the contract.
```

This is old territory. Pure functions, side effects, effect systems, explicit IO, and render-purity rules in UI frameworks all point at versions of the same idea. I am interested in the everyday version: when a caller sees a method, what assumptions are safe?

## Types For Values, Purity For Calls

Static types make some assumptions about values visible.

A dynamically typed program still has value assumptions. If I add two values, call `.Length`, index into a collection, or pass a value to a method, I am assuming those values support those operations.

Static types move some of those assumptions into declarations the compiler can check.

Purity plays a similar role for calls.

When I retry a method, cache its result, call it twice, pass it to LINQ, run it in parallel, or move it earlier in the program, I am assuming something about the method's behavior. The code may use phrases like "this is just a calculation," "this is safe to retry," "this leaves objects unchanged," or "this predicate only checks a condition." Those phrases still name behavioral contracts.

By "pure" here, I mean the practical code-review version:

```text
all inputs explicit
deterministic observable outcome out
externally visible effects absent
```

The outcome may be a returned value or a deterministic failure. Totality is a separate contract. So are performance, thread safety, naming, stable equality, and ease of use.

The useful engineering promise is narrower: the call behaves like a calculation.

That matters because real programs transform calls. They retry operations, cache results, delay work, reorder calculations, replay historical inputs, parallelize loops, and pass functions into other abstractions.

Those transformations need support. A retry helper assumes it is allowed to call the operation again. A cache assumes a previous result can be reused for the same key. A sorting routine assumes its comparer is consistent. A LINQ query assumes its predicate can be called according to the query's evaluation strategy.

Purity is one contract that makes many of those assumptions valid by default. It preserves more legal moves for the caller.

It also composes in a predictable way:

```text
pure + pure = pure
pure + effectful = effectful
effectful + effectful = effectful
```

This is the practical sense in which effects "contaminate" a call. Nothing moral is happening. The caller contract simply gets larger. Once a calculation reads the clock, writes a file, calls a service, mutates shared state, or invokes an effectful callback, callers need to account for that larger behavior.

That is why it can be useful to keep pure code near other pure code. Useful calculation boundaries stay small, stable, and easy to move.

## Retry And Repetition

Retry logic makes the distinction concrete.

Real retry code needs backoff, cancellation, and exception filtering. This example only illustrates repetition:

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

That is a perfectly good contract. The important part is that callers need some contract before they transform the call.

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

## Boundaries And Hidden Inputs

Method signatures are useful. In C#-style code, they tell us parameter types, return types, and awaitable shapes. Nullable reference type annotations can also make some assumptions visible enough for warnings and review.

They usually leave out whether a method reads the clock, depends on `CurrentCulture`, calls a database, writes a file, mutates shared state, or leaves some other observable effect behind.

Take a method like this:

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

That method makes a strong promise. Given the same `order`, `taxRate`, and `discount`, it behaves the same way. It uses only the values in its parameter list.

Now compare it to this:

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

The arithmetic is familiar. The contract is larger. The method still returns `Money`, and the call now also has latency, failure behavior, freshness questions, and dependencies on external state.

That may be exactly what you want in application-service code. The receiver object matters. A method on `CheckoutService` carries different expectations from a method on `CheckoutMath`. Constructor-injected dependencies are visible at the object boundary; `DateTimeOffset.UtcNow` or `Guid.NewGuid()` inside a calculation stay hidden inside the call.

The useful question is whether the caller can treat the method as just a calculation.

This is where functional core / imperative shell helps. The shell gathers facts from the world and performs visible effects. The core takes explicit values and returns a calculation, decision, or plan.

```text
Use dependency injection in the shell.
Use explicit values in the core.
```

Constructor injection is appropriate for application services, repositories, adapters, clients, and orchestration code. Explicit method parameters are often better for domain policy, pricing, validation, authorization, scheduling, retry rules, and other code where the main job is to decide.

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

Expected failure can be hidden too:

```csharp
Customer LoadCustomerOrThrow(Guid id)
Customer? FindCustomer(Guid id)
bool TryLoadCustomer(Guid id, out Customer customer)
CustomerResult LoadCustomer(Guid id)
```

Those shapes create different expectations. Normal caller behavior should usually be visible somewhere: in the name, in the return type, in documentation, or in the boundary where the method lives.

## Tooling And Restraint

Some languages expose some behavioral contracts. In C#, `Task<T>` and other awaitable shapes change how a method is called. Nullable reference type annotations make some assumptions visible enough for warnings while runtime behavior stays the same.

In many procedural and object-oriented languages, purity rarely appears in the type. So we express it indirectly through naming, documentation, boundaries, tests, code review, and analyzers.

Some languages and tools track purity or effects directly. That gives stronger guarantees. In the kind of code I am talking about here, the usual version is more modest: keep pure calculations identifiable, keep effects near the boundary, and avoid pretending the two calls have the same contract.

Annotations and analyzers can help in narrow cases. Depending on the rule set and known APIs, they can catch obvious cases, warn on ignored return values, flag implicit culture usage, or encode project conventions. Full semantic proof for arbitrary programs remains outside their reach.

That is fine. The goal is better signals rather than theorem proving.

An incorrect annotation is worse than an absent annotation. If a `[Pure]`-style annotation becomes aspirational instead of checked, it becomes documentation that can lie. I would rather a tool say `Unknown` than incorrectly bless a method as pure.

There is also a tradeoff. Making behavior visible can make code more verbose. Passing `now`, `culture`, `taxRate`, or `discount` explicitly can be overkill. Expose the dependencies that materially affect correctness, repeatability, reuse, or caller obligations.

The bad version of this idea is easy to write:

```csharp
var a = Step1(input);
var b = Step2(a);
var c = Step3(b);
var d = Step4(c);
```

Purity alone is insufficient. A pure function should still earn its name. `CalculateTotal`, `DecideRenewal`, `ValidatePolicy`, and `PlanShipment` are useful boundaries. `Step1` through `Step4` usually are filler.

I would avoid annotating every method, forcing every dependency into parameters, or turning clear imperative code into function confetti.

Effects belong in programs. They belong in the parts of the program where the caller expects interaction with the world.

Pure methods and effectful methods make different promises. Pure methods are value-like. Effectful methods are interaction-like. Both are useful, and they preserve different caller assumptions.

The goal is fewer surprising method calls.
