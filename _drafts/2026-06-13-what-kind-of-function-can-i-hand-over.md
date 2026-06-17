---
title: "What Kind of Function Can I Hand Over?"
date: 2026-06-13
description: "Pure functions compose by passing values. Effectful functions compose by sequencing state changes."
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/), [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result/)

In Part 1, I wrote about `List<T>` as a monad. The useful idea was broader than the word "monad" by itself: a context can know how to apply a function. A list applies a function to many values. An option-like value may apply a function zero or one times. A result-like value may skip the function after failure.

In each case, I give some context a function, and the context controls the application. This post is about the other side of that bargain:

```text
What kind of function am I safe to hand over?
```

If the function is pure, the context has more freedom. It can call the function now, later, once, many times, lazily, or as part of a larger composition. If the function has effects, the context's strategy becomes observable. How many times it calls the function, when it calls it, whether it retries, whether it short-circuits, whether it runs in parallel - those details may now matter.

That is where purity matters. Real programs have to talk to the world, and pure functions and effectful functions compose differently.

The short version is:

```text
Pure functions compose by passing values.
Effectful functions compose by sequencing state changes.
```

Both are useful, and they make different promises.

## The hidden world parameter

By "pure," I mean the practical code-review definition: when the function returns normally, the same explicit inputs produce the same returned value, and the call leaves no externally visible effect behind.

A pure function has this shape:

```text
Input -> Output
```

An effectful function has a larger shape. If it reads from the world, it is closer to:

```text
Input + World -> Output
```

If it writes to the world, it is closer to:

```text
Input + World -> Output + World'
```

Passing `World` around in ordinary C# would be absurd. The model is still useful because it explains why effects compose differently. A database row, the current time, current culture, a feature flag, a file, a cache entry, or an API response can all become ordinary values. Obtaining those values is itself situated.

Once the world has been observed, a calculation can be pure:

```csharp
var taxRate = _taxService.GetRate(order.Address);
var total = CalculateTotal(order, taxRate, discount);
```

The first line observes the world. The second line decides with values. The effect remains, and the boundary becomes explicit.

## Effects introduce a state protocol

Pure functions compose by passing values:

```text
Input -> Output
```

Effectful functions compose by sequencing state changes:

```text
Input + World -> Output + World'
```

That means effectful calls often come with a protocol:

```text
configuration must be loaded before this runs
this must run inside a transaction
this must not run twice
this must run before the event is published
this must observe the same snapshot as the previous read
this must not run in parallel without synchronization
```

Those protocols are necessary in real programs. A useful program has to read files, query databases, call APIs, send emails, and persist changes. Trouble starts when the protocol is invisible.

Pure code still has order. The order is usually visible in the values:

```text
Order -> Subtotal -> Total
```

Effectful code can add another kind of order:

```text
load config before pricing
open transaction before saving
publish event after commit
do not call twice
do not run concurrently
```

That order may be real and absent from the values. If the protocol lives in a controller, job handler, repository, adapter, or application service, that may be exactly the right place. Those parts of the program are supposed to orchestrate effects.

If the protocol is buried inside code that callers want to treat as a calculation, validation rule, predicate, formatter, pricing rule, policy decision, or state transition, then a value-like call has become situated.

For example:

```csharp
public sealed class PricingService
{
    private readonly PricingConfig _config;

    public void ReloadPricingConfig()
    {
        _config.ReloadFromDisk();
    }

    public Money CalculateTotal(Order order)
    {
        return order.Subtotal
            .ApplyDiscount(_config.CurrentDiscount)
            .ApplyTax(_config.CurrentTaxRate);
    }
}
```

There is real dataflow here:

```text
ReloadPricingConfig()
    -> _config
        -> CalculateTotal(order)
```

The call site only shows:

```csharp
pricing.CalculateTotal(order)
```

The code may be valid service-layer code, and it is situated. To reason about it, the caller may need to know whether the configuration was loaded, which version was loaded, whether another thread could reload it, whether this call saw the old or new version, and what happens if reload fails halfway.

A value-like version moves the facts to the call boundary:

```csharp
public static Money CalculateTotal(
    Order order,
    Discount discount,
    TaxRate taxRate)
{
    return order.Subtotal
        .ApplyDiscount(discount)
        .ApplyTax(taxRate);
}
```

The shell can still be situated:

```csharp
public Money CalculateTotalForCheckout(Order order)
{
    var discount = _config.CurrentDiscount;
    var taxRate = _config.CurrentTaxRate;

    return Pricing.CalculateTotal(order, discount, taxRate);
}
```

The effect remains. The protocol moved to the boundary.

## Dependencies and facts are different

Dependency injection can make a dependency explicit:

```csharp
public PricingService(ITaxRateProvider taxRates)
```

That tells me this service may get tax-rate facts from a provider. The specific tax rate used by a calculation is a separate fact. A dependency is a pipe. A fact is a value that came through the pipe.

```text
Dependency:
    ITaxRateProvider

Fact:
    TaxRate = 7%, version 42, observed at this point in the workflow
```

Dependency injection makes services visible at the object boundary. Explicit parameters make facts visible at the call boundary. Those are different kinds of visibility.

This method is situated:

```csharp
public Money CalculateTotal(Order order)
```

because the important facts may be hidden behind the provider:

```text
Order
+ tax rate currently returned by provider
+ provider state
+ cache state
+ transaction state
+ freshness policy
-> Money
```

That may be exactly right for application-service code. When the important part is the pricing rule, this version makes the fact visible:

```csharp
public static Money CalculateTotal(Order order, TaxRate taxRate)
```

The shell observes facts through dependencies. The core decides with facts. That is the distinction.

## Current value is still a contract

Sometimes the writer of the value is irrelevant. If I call a repository, I may simply want the current persisted data. If I call an API client, I may simply want the API response. If I call a configuration provider, I may simply want the current configuration. That is fine. Hiding those details is often the point of the abstraction.

"Current value" is still a contract. It means the result may change between calls even when the explicit arguments stay the same. That may be fine for display code. It may be wrong for billing, auditing, replay, cache keys, signatures, policy comparison, deterministic tests, historical reports, or security decisions.

Load-bearing hidden dataflow creates the risk.

## Read the world at the edge; decide with values

A lot of effect management comes down to choosing where to perform effects.

Reading configuration is situated. Using configuration can be pure.

```csharp
var config = LoadConfiguration();
var delay = RetryPolicy.CalculateDelay(attempt, config.Backoff);
```

Checking the clock is situated. Deciding with a timestamp can be pure.

```csharp
var now = _clock.UtcNow;
var expired = SubscriptionPolicy.IsExpired(subscription, now);
```

Calling a tax service is situated. Applying a tax rate can be pure.

```csharp
var taxRate = _taxService.GetRate(order.Address);
var total = CalculateTotal(order, taxRate, discount);
```

Reading a template file is situated. Rendering with a template can be pure.

```csharp
var template = File.ReadAllText("Templates/Invoice.html");
var html = RenderInvoice(order, template, culture, issuedAt);
```

The effects remain. They moved to a boundary.

A useful rule of thumb is:

```text
Read the world at the edge.
Decide with values.
Write the world at the edge.
```

This tradeoff matters. Passing `now`, `culture`, `taxRate`, `discount`, `template`, and `config` everywhere can become noise. When a decision needs to be replayed, cached, tested, audited, compared, batched, simulated, or handed to another abstraction, making the facts explicit often pays for itself.

## What kind of function can I hand over?

Higher-order functions are where this becomes impossible to ignore. Most programmers say "sorting," "filtering," "caching," or "parallel query." Either way, they pass comparers, predicates, selectors, factories, and accumulators.

The important part is that another piece of code now controls the call.

| API shape                  | Function handed over | What the abstraction controls     |
| -------------------------- | -------------------- | --------------------------------- |
| `Sort(comparer)`           | comparer             | comparison count and order        |
| `Where(predicate)`         | predicate            | evaluation timing and count       |
| `Select(selector)`         | projection           | evaluation timing and count       |
| `GetOrAdd(valueFactory)`   | value factory        | whether or how often to compute   |
| `AsParallel().Select(...)` | projection           | thread, order, and concurrency    |
| `Aggregate(...)`           | accumulator          | grouping, partitioning, and order |

A pure callback can usually tolerate that loss of control. An effectful callback can still be correct, with the abstraction's call strategy becoming part of the program's behavior.

Consider a pure function:

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

I can hand that calculation to several contexts:

```csharp
var total = CalculateTotal(order, taxRate, discount);

var totals = orders.Select(order =>
    CalculateTotal(order, taxRate, discount));

var key = new TotalKey(order.Id, taxRate.Id, discount.Code);

var cached = cache.GetOrAdd(key, _ =>
    CalculateTotal(order, taxRate, discount));

var retried = Retry(() =>
    CalculateTotal(order, taxRate, discount), attempts: 3);
```

Those contexts can call it in their own way without turning their call strategy into business behavior.

Now compare an effectful version:

```csharp
public Money CalculateTotal(Order order)
{
    _audit.Record("Calculating total");

    var taxRate = _taxService.GetRate(order.ShippingAddress);

    return order.Subtotal.ApplyTax(taxRate);
}
```

This may be valid service code. It is just less freely movable. If `Select` is lazy, the audit timing changes. If `GetOrAdd` calls the factory more than once, the audit or service call may happen more than once. If `Retry` repeats the operation, the tax service may be called repeatedly. If this runs in parallel, the audit and service dependencies may matter.

The function can still be used. Now I care how the context applies it.

## Number, timing, and order

Pure functions make the number, timing, and order of calls less important. Effects make them part of the contract.

For a pure function, calling it twice usually changes performance more than program meaning. Calling it now or later usually produces the same result. Reordering it with another pure function is usually harmless, aside from cost or deterministic failure.

For an effectful function, those details may be the whole point. Calling it twice may send two emails. Calling it later may read a different clock or database state. Reordering it may change persisted state.

Retry logic makes this concrete. Real retry code needs backoff, cancellation, and exception filtering. This example only illustrates repetition.

```csharp
var total = Retry(
    () => CalculateTotal(order, taxRate, discount),
    attempts: 3);

var receipt = Retry(
    () => ChargeCard(payment),
    attempts: 3);
```

Both calls fit behind a `Func<T>`. The type leaves open the important question:

```text
Is this operation safe to repeat?
```

If `CalculateTotal` is a pure calculation, repeating it sends no extra email, writes no extra row, publishes no extra event, and leaves caller-owned state alone. Retrying may still be useless if the failure is deterministic. Purity has limits: it leaves a calculation just as partial, expensive, or fallible as before. The repeat itself duplicates no external effect.

`ChargeCard` is different. It may call a payment processor, reserve funds, write a ledger entry, send a receipt, or publish an event. Repeat it and you may charge twice.

`ChargeCard` can still be a good boundary. The caller just needs a different contract. A payment operation can be safe to retry when it uses an idempotency key and the receiving system honors it. Here I am using idempotency in the distributed-systems sense: repeating the same logical request produces the same intended external state.

That is a useful contract. It gives an effectful call one pure-like property: repetition becomes safer. Callers need some contract before they delegate or transform the call.

## The purity version of function color

Bob Nystrom's ["What Color is Your Function?"](https://journal.stuffwithstuff.com/2015/02/01/what-color-is-your-function/) is about async. The useful shape is broader: a property of a function can stop being a local implementation detail and start affecting composition.

In his article, async affects how a function can be called. Here, effects affect what another abstraction is allowed to do with the function.

```text
Async changes call mechanics.
Effects change call assumptions.
```

A pure function can be applied more freely. An effectful function can still be correct when another contract makes the abstraction's call strategy safe.

From the caller's point of view, the propagation rule is:

```text
pure + pure = pure
pure + effectful = effectful
```

Or in the vocabulary of this post:

```text
value-like + value-like = value-like
value-like + situated = situated
```

A calculation can call another calculation and remain value-like. Once it reads the clock, calls a service, writes telemetry, mutates shared state, or invokes an effectful callback, the composed method is now situated.

That makes a different promise.

## Everyday places this already happens

Sorting is one of the oldest everyday examples:

```csharp
customers.Sort((left, right) =>
    string.Compare(left.LastName, right.LastName, StringComparison.Ordinal));
```

The comparison needs to give consistent answers for the same inputs. If it reads the clock, consults mutable global state, or changes shared state that later comparisons depend on, sorting becomes harder to reason about because algorithm details become observable.

For example:

```csharp
customers.Sort((left, right) =>
{
    _audit.Record($"Compared {left.Id} and {right.Id}");
    return _riskService.GetScore(left).CompareTo(_riskService.GetScore(right));
});
```

If that audit record is meaningful business data, this is a poor place for it. The sorting algorithm never promised how many comparisons it would perform. Comparison count and order are now observable, so the sort routine's internal strategy has become part of the behavior.

LINQ predicates and selectors make the same issue visible:

```csharp
var matching = orders.Where(order =>
{
    _audit.Record($"Checked order {order.Id}");
    return order.Total > 500;
});
```

The predicate may run later than the line that creates `matching`. It may run again if the sequence is enumerated twice. A later operator may short-circuit before every order is checked.

Cache factories are another good example. `ConcurrentDictionary<TKey, TValue>.GetOrAdd` may call its value factory more than once under concurrency, even though only one value is stored:

```csharp
var summary = cache.GetOrAdd(id, key =>
    BuildCustomerSummary(key));
```

That is fine when the factory is pure or at least safe to duplicate. It is a bad place to hide a command:

```csharp
var summary = cache.GetOrAdd(id, key =>
{
    SendCacheMissEmail(key);
    return BuildCustomerSummary(key);
});
```

Parallel queries raise the stakes:

```csharp
var totals = orders.AsParallel()
    .Select(order => CalculateTotal(order, taxRate, discount));
```

If the selector is pure, parallelism is mostly a scheduling and performance question. If the selector writes shared state, calls non-thread-safe APIs, or depends on result order, parallelism becomes a correctness question.

Reducers follow the same pattern. Once an abstraction partitions or combines work, the accumulator may need additional contracts such as statelessness, an identity value, and associativity. This shows the broader rule:

```text
when I hand a function to an abstraction, the function's contract determines which call strategies are legal
```

## Local mutation can stay local

Purity is about observable behavior more than implementation style. A pure implementation can use local mutation, structural sharing, memoization, pooling, or other optimizations as long as hidden inputs and externally visible effects stay outside the caller's view.

Performance is still a real design constraint. Computation still has a cost.

Local mutation can be compatible with purity when it stays local:

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

The function mutates `builder`. That mutation is local, and the returned result is immutable. Assuming `Item` is itself treated as an immutable value, the intermediate mutation stays hidden from the caller.

This is different:

```csharp
public static void AddItem(List<Item> items, Item item)
{
    items.Add(item);
}
```

That mutates caller-owned state. The relevant question is whether the caller can observe the mutation and must account for it.

## Functional core / imperative shell

Functional core / imperative shell is one practical response to the thesis.

The shell is situated. It reads files, talks to databases, checks the clock, calls services, handles retries, writes logs, and sends messages. The core is value-like. It receives values and returns values: prices, decisions, validation results, state transitions, schedules, and plans.

The whole program is still effectful. The important decisions no longer depend on invisible state protocols through the middle of the program.

Objects, dependency injection, repositories, and ambient context all still have a place. A repository is supposed to know about a database. An HTTP client is supposed to know about the network. A controller is supposed to orchestrate a request. A job handler is supposed to sequence effects. Those calls are situated by design.

The risk appears when situated behavior is buried inside code that callers want to treat as value-like: pricing rules, validation, authorization, scheduling, formatting, policy decisions, state transitions, and calculations.

A rule of thumb:

```text
Use dependency injection for services that observe or change the world.
Use explicit values for facts that important decisions decide with.
```

Or more compactly:

```text
The shell observes facts.
The core decides with facts.
```

## Restraint

The bad version of this idea is easy to write:

```csharp
var a = Step1(input);
var b = Step2(a);
var c = Step3(b);
var d = Step4(c);
```

Purity alone cannot rescue that code. A pure function should still earn its name. `CalculateTotal`, `DecideRenewal`, `ValidatePolicy`, and `PlanShipment` are useful boundaries. `Step1` through `Step4` usually are filler.

There is also a tradeoff. Making behavior visible can make code more verbose. Passing `now`, `culture`, `taxRate`, `discount`, or `template` explicitly can be overkill.

Expose the facts that materially affect correctness, repeatability, replay, caching, auditing, reuse, or caller obligations. Keep ordinary imperative code when it is clear. Avoid method-by-method annotation, parameterizing every dependency, or turning straightforward code into function confetti.

Effects belong in real programs. They belong in the parts of the program where callers expect interaction with the world.

The point is to keep important decisions from depending on load-bearing invisible dataflow.

The goal is to keep invisible state protocols out of code that should have been a calculation.
