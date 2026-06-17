---
title: "What Kind of Function Can I Hand Over?"
date: 2026-06-13
description: "Pure functions compose by passing values. Effectful functions compose by sequencing state changes."
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/), [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result/)

In Part 1, I wrote about `List<T>` as a monad. The useful idea was broader than the word "monad" by itself: some abstractions come with rules for applying and composing functions. With `Map`, `List<T>` applies a function to each element. A maybe-like value may apply it zero or one times. A result-like value may stop after the first failure.

Once I hand one of those abstractions a function, the abstraction's call strategy matters. It may call the function later, more than once, not at all, or as part of a larger composition. This post asks a narrower question:

```text
What kind of function can I hand over?
```

Pure functions can still take plenty of context through explicit parameters. What changes the composition story is hidden dependence on external state, time, services, or shared mutable data, plus any visible effect beyond the returned value.

If a function is pure, the abstraction receiving it usually has more freedom. It can defer the call, retry it, cache it, or combine it with other work without changing observable behavior. If the function has effects, those choices can become part of the program's behavior.

That is where purity matters. Real programs have to talk to the world, and pure functions and effectful functions compose differently.

The short version is:

```text
Pure functions compose by passing values.
Effectful functions compose by sequencing state changes.
```

Both are useful. They just make different promises.

## Explicit inputs and hidden inputs

By "pure," I mean the practical code-review definition: when the function returns normally, the same explicit inputs produce the same returned value, and the call leaves no externally visible effect behind.

Explicit inputs are still context in the ordinary English sense. The point is that they are visible at the call site instead of being hidden in ambient state, mutable dependencies, or I/O.

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

No one literally passes `World` around. The model is still useful because it distinguishes explicit dataflow from hidden interaction with the environment. A database row, the current time, current culture, a feature flag, a file, a cache entry, or an API response can all become ordinary values. Obtaining those values is itself situated.

Once the world has been observed, a calculation can be pure:

```csharp
var taxRate = _taxService.GetRate(order.Address);
var total = CalculateTotal(order, taxRate, discount);
```

The first line observes the world. The second line decides with values. The effect remains, and the boundary becomes explicit.

## Effects introduce an execution protocol

Pure functions compose by passing values:

```text
Input -> Output
```

Effectful functions compose by sequencing state changes:

```text
Input + World -> Output + World'
```

That often brings an execution protocol with it:

```text
configuration must be loaded before this runs
this must run inside a transaction
this must not run twice
this must run before the event is published
this must observe the same snapshot as the previous read
this must not run in parallel without synchronization
```

Those protocols are necessary in real programs. Useful programs have to read files, query databases, call APIs, send emails, and persist changes. The harder cases are the ones where that protocol is easy to miss.

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

The calling code can still observe the world:

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

Sometimes the writer of the value is irrelevant. If I call a repository, I may simply want the current persisted data. If I call an API client, I may simply want the API response. If I call a configuration provider, I may simply want the current configuration. That is often the right abstraction.

"Current value" is still a contract. It means the result may change between calls even when the explicit arguments stay the same. That may be fine for display code. It may be wrong for billing, auditing, replay, cache keys, signatures, policy comparison, deterministic tests, historical reports, or security decisions. The risk is not abstraction by itself. The risk is load-bearing hidden dataflow in places that callers want to treat like calculations.

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

One useful pattern is:

```text
Read the world at the edge.
Decide with values.
Write the world at the edge.
```

This tradeoff matters. Passing `now`, `culture`, `taxRate`, `discount`, `template`, and `config` everywhere can become noise. When a decision needs to be replayed, cached, tested, audited, compared, batched, simulated, or handed to another abstraction, making the facts explicit often pays for itself.

So far this is mostly about ordinary method calls. The same tradeoff becomes sharper when the value being passed around is itself a function.

## What kind of function can I hand over?

Higher-order APIs make this impossible to ignore. They accept comparers, predicates, selectors, factories, and accumulators, and then decide when and how those callbacks run.

| API shape                  | Function handed over | What the abstraction controls     |
| -------------------------- | -------------------- | --------------------------------- |
| `Sort(comparer)`           | comparer             | comparison count and order        |
| `Where(predicate)`         | predicate            | evaluation timing and count       |
| `Select(selector)`         | projection           | evaluation timing and count       |
| `GetOrAdd(valueFactory)`   | value factory        | whether or how often to compute   |
| `AsParallel().Select(...)` | projection           | thread, order, and concurrency    |
| `Aggregate(...)`           | accumulator          | grouping, partitioning, and order |

A pure callback can usually tolerate those invocation freedoms. An effectful callback can still be correct, but the abstraction's call strategy becomes part of the program's behavior.

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

## Why number, timing, and order matter

Pure functions make the number, timing, and order of calls less important to observable behavior. Effects make them part of the contract.

For a pure function, calling it twice usually changes cost more than program meaning. Calling it now or later usually produces the same result. Reordering it with another pure function is usually harmless, aside from cost, deterministic failure, or nontermination.

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

If `CalculateTotal` is a pure calculation, repeating it sends no extra email, writes no extra row, publishes no extra event, and leaves caller-owned state alone. Retrying may still be useless if the failure is deterministic. Purity is not magic: it leaves a calculation just as partial, expensive, or fallible as before. The repeat itself duplicates no external effect.

`ChargeCard` is different. It may call a payment processor, reserve funds, write a ledger entry, send a receipt, or publish an event. Repeat it and you may charge twice.

`ChargeCard` can still be a good boundary. The caller just needs a different contract. A payment operation can be safe to retry when it uses an idempotency key and the receiving system honors it. Here I am using idempotency in the distributed-systems sense: repeating the same logical request produces the same intended external state.

That is a useful contract. It gives an effectful call one pure-like property: repetition becomes safer. More broadly, once another abstraction controls repetition, ordering, laziness, or scheduling, the callback's contract starts to matter.

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

If that audit record is meaningful business data, this is a poor place for it. `List<T>.Sort` uses an unstable sort, so equal elements are not guaranteed to preserve their relative order, and the comparison pattern is tied to the algorithm. Comparison count and order are now observable, so the sort routine's internals have become part of the behavior.

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
when I hand a function to an abstraction, the function's contract determines which call strategies are safe
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

Functional core / imperative shell is one practical shape that falls out of this way of thinking.

The shell is situated. It reads files, talks to databases, checks the clock, calls services, handles retries, writes logs, and sends messages. The core is value-like. It receives values and returns values: prices, decisions, validation results, state transitions, schedules, and plans.

The whole program is still effectful. The important decisions no longer depend on invisible state protocols through the middle of the program.

Objects, dependency injection, repositories, and ambient context all still have a place. A repository is supposed to know about a database. An HTTP client is supposed to know about the network. A controller is supposed to orchestrate a request. A job handler is supposed to sequence effects. Those calls are situated by design.

The risk appears when situated behavior is buried inside code that callers want to treat as value-like: pricing rules, validation, authorization, scheduling, formatting, policy decisions, state transitions, and calculations.

A workable default is:

```text
Use dependency injection for services that observe or change the world.
Use explicit values for facts that important decisions depend on.
```

Or more compactly:

```text
The shell observes facts.
The core decides with facts.
```

## Practical takeaway

None of this means every fact should become a parameter or every service should disappear behind a new layer. Sometimes "current value" is the right contract, and sometimes a small imperative method is clearer than a more explicit API.

The useful question is narrower: if I hand this function to another abstraction, or if I want to retry, cache, replay, test, or parallelize it, what facts and effects need to stay visible for the code to remain correct?

When that answer matters, moving observation of the world outward and letting the decision itself work with ordinary values usually makes the code easier to compose.
