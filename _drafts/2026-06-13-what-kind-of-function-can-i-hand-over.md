---
title: "What Kind of Function Can I Hand Over?"
date: 2026-06-13
description: "When another API gets to call your function, hidden context starts to matter."
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/), [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result/)

In Part 1 and Part 2, the focus was on `List<T>`, `Maybe<T>`, and `Result<TSuccess, TError>`. Those types do more than carry values. Through operations such as `Map` and `Bind`, they also control how your function is called and how the next step is chained.

With `List<T>`, a function may run once per element. With `Maybe<T>`, it may not run at all. With `Result<TSuccess, TError>`, a failure may stop the chain before the next function runs.

That raises the question in this article's title: what kind of function can I hand over?

The distinction here is straightforward. Some functions only need the values you pass in. Others also depend on hidden inputs such as clock time, file contents, database state, mutable shared state, or other effects. Once another type, API, or layer gets to decide when and how your function runs, that difference starts to matter.

## Explicit and implicit inputs

By "pure" I mean this in a code-review sense: if you could replace the call with a lookup from explicit inputs to return values, and the program's observable behavior would stay the same, then the function is pure enough for this discussion.

A pure function can still take plenty of context through its parameters. What matters here is that the context it depends on is explicit at the call site.

A pure function has this shape:

```text
Input -> Output
```

An effectful function may also depend on inputs that are not present in its parameter list. It may read current time, file contents, database state, global configuration, cache state, or service responses. It may also change some of those things for later code.

If it reads from the world, it is closer to:

```text
Input + World -> Output
```

If it reads and writes to the world, it is closer to:

```text
Input + World -> Output + World'
```

You do not literally pass a `World` object in ordinary code. The point of the model is only that some inputs are explicit and some come from the surrounding environment.

Reading a file is a straightforward example. The path may be explicit, but the file contents are still an implicit input:

```csharp
var template = File.ReadAllText(path);
var html = RenderInvoice(order, template, culture, issuedAt);
```

`ReadAllText` depends on the current file system. `RenderInvoice` can still be a normal calculation once the template has been turned into an ordinary value.

The same shape shows up with clocks, tax services, repositories, feature flags, and configuration. Once those facts have been observed, later code can often work with ordinary values:

```csharp
var taxRate = _taxService.GetRate(order.Address);
var total = CalculateTotal(order, taxRate, discount);
```

## Effects propagate through composition

This matters in combinations too, not just in isolated functions.

If one step is pure and another step reads or writes the world, the combined function is still effectful. The pure step does not remove the hidden input or the visible effect. It only means part of the overall work is an ordinary calculation.

For example, this helper can still be pure:

```csharp
public static Money CalculateTotal(Order order, TaxRate taxRate)
{
    return order.Subtotal.ApplyTax(taxRate);
}
```

and this wrapper is still effectful:

```csharp
public Money CalculateTotalForCheckout(Order order)
{
    var taxRate = _taxService.GetRate(order.Address);
    return CalculateTotal(order, taxRate);
}
```

The call to `CalculateTotal` is value-like. The combined method is not, because it still depends on whatever `_taxService` returns at that moment.

The same thing happens in the other direction. If a pure function prepares input for an effectful call, the whole operation is still effectful:

```csharp
var message = RenderReceipt(order, total);
_emailGateway.Send(message);
```

That is one reason effects tend to propagate outward through a program once they are mixed into a workflow. A pure helper can stay pure locally, but the larger function that combines it with effectful steps still has to be treated as effectful.

## Why execution context matters

Once a function reads or writes hidden state, the caller has more to manage than arguments. The caller also has to arrange the surrounding world so the function runs against the right state and in the right relationship to other effectful steps.

Two effectful steps can depend on each other without passing a value directly between them. One step writes a file, row, cache entry, or in-memory field. Another step later reads it. Or one step publishes an event that must only happen after a transaction commits. In cases like that, timing, duplication, and ordering become part of correctness.

That is why code picks up requirements such as:

```text
configuration must be loaded before this runs
this must run inside a transaction
this must not run twice
this must run before the event is published
this must observe the same snapshot as the previous read
this must not run in parallel without synchronization
```

Those requirements are ordinary parts of software. A method can still hide them, though, which makes the call look simpler than the behavior really is.

When that sequencing lives in a controller, job handler, repository, or adapter, it is sitting next to code that already deals with the outside world. When the same sequencing is buried inside something callers want to treat as a calculation, policy decision, predicate, formatter, or state transition, the call carries more context than its signature suggests.

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

The code may be perfectly fine service-layer code. To reason about it, though, the caller may need to know whether the configuration was loaded, which version was loaded, whether another thread could reload it, whether this call saw the old or new version, and what happens if reload fails halfway.

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

The dataflow is the same, but the facts needed by the calculation are now visible in the signature.

## Dependencies and facts

Dependency injection can make a dependency explicit:

```csharp
public PricingService(ITaxRateProvider taxRates)
```

That tells me this service may obtain tax-rate information from a provider. The concrete rate used by a calculation is a separate fact. The dependency tells me where a value may come from. The fact is the value that actually came back at a particular point in the workflow.

Dependency injection makes services visible at the object boundary. Explicit parameters make concrete facts visible at the call boundary.

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

In some cases, "whatever the provider currently returns" is exactly the right contract. In others, especially when a result needs to be replayed, audited, compared, cached, or tested deterministically, the observed fact matters more than the dependency that supplied it.

That is one reason people often move reads outward and let inner code work with values.

```csharp
var config = LoadConfiguration();
var delay = RetryPolicy.CalculateDelay(attempt, config.Backoff);
```

```csharp
var now = _clock.UtcNow;
var expired = SubscriptionPolicy.IsExpired(subscription, now);
```

In both examples, one layer observes facts through dependencies and another layer decides with those facts as values.

This tradeoff matters. Passing `now`, `culture`, `taxRate`, `discount`, `template`, and `config` everywhere can become noise. When a decision needs to be replayed, cached, tested, audited, compared, batched, simulated, or handed to another piece of code, making the facts explicit often pays for itself.

So far this is mostly about ordinary method calls. The same tradeoff becomes sharper when the value being passed around is itself a function.

## What kind of function can I hand over?

Higher-order APIs make the question concrete. They accept comparers, predicates, selectors, factories, and accumulators, then decide when, how often, and on which thread those callbacks run.

| API shape                  | Function handed over | What the API controls             |
| -------------------------- | -------------------- | --------------------------------- |
| `Sort(comparer)`           | comparer             | comparison count and order        |
| `Where(predicate)`         | predicate            | evaluation timing and count       |
| `Select(selector)`         | projection           | evaluation timing and count       |
| `GetOrAdd(valueFactory)`   | value factory        | whether or how often to compute   |
| `AsParallel().Select(...)` | projection           | thread, order, and concurrency    |
| `Aggregate(...)`           | accumulator          | grouping, partitioning, and order |

When the callback is pure, the receiving API usually has more freedom. It can often defer, repeat, cache, or parallelize the call without changing the meaning of the program. An effectful callback can still be correct, but those same choices start to matter directly.

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

Those contexts can call it in their own way because the interesting behavior is still in the returned value, not in the act of calling it.

Now compare an effectful version:

```csharp
public Money CalculateTotal(Order order)
{
    _audit.Record("Calculating total");

    var taxRate = _taxService.GetRate(order.ShippingAddress);

    return order.Subtotal.ApplyTax(taxRate);
}
```

This may be valid service code. It is just less portable across call strategies. If `Select` is lazy, the audit timing changes. If `GetOrAdd` calls the factory more than once, the audit or service call may happen more than once. If `Retry` repeats the operation, the tax service may be called repeatedly. If this runs in parallel, the dependencies may need to be thread-safe.

The function still works. What changes is the contract around it. Number of calls, timing, and ordering now matter to correctness, not just to cost.

With a pure function, extra calls usually change cost more than meaning. With an effectful function, extra calls may send another email, read a different clock time, or persist a different state.

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

That is a useful contract. It gives an effectful call one pure-like property: repetition becomes safer. More broadly, once another piece of code controls repetition, ordering, laziness, or scheduling, the callback's contract starts to matter.

## Everyday examples

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

Reducers follow the same pattern. Once a library or API partitions or combines work, the accumulator may need additional contracts such as statelessness, an identity value, and associativity. More generally, once some other piece of code controls the call strategy, the function's contract determines which strategies are safe.

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

This is where functional core / imperative shell becomes useful.

The shell handles files, databases, clocks, HTTP calls, retries, logs, and messages. The core receives already observed facts and computes decisions, validation results, state transitions, schedules, or plans from them.

The whole program is still effectful. The difference is that important decisions are less entangled with hidden timing and ordering requirements in the middle of the codebase.

Repositories, HTTP clients, controllers, job handlers, and similar pieces still have a place. They are the parts of the system that naturally deal with the outside world. The tension usually appears when that situated behavior is buried inside code that callers want to treat as a calculation, rule, predicate, formatter, policy decision, or state transition.

None of this means every fact should become a parameter or every service should disappear behind a new layer. Sometimes "current value" is the right contract, and sometimes a small imperative method is clearer than a more explicit API.

The narrower question is the one from the title: if I hand this function to another type, API, or layer, which facts and effects need to stay visible for the code to remain correct?

When that question matters, reading from the world near the boundary and letting the decision itself run on ordinary values usually gives the rest of the program more room to compose the code safely.
