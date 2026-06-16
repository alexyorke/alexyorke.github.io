---
title: "What Kind of Function Can I Hand Over?"
date: 2026-06-13
description: "Purity matters most when I stop controlling the call."
---

This post is about what happens when I hand a function to code I do not control.

If I call a method directly, once, in an obvious order, I may not need a formal purity contract. I can read the method name, preserve the order of steps, and keep the effect boundaries in my head.

But if I pass that method to another abstraction: a sort, a filter, a cache, a retry helper, a parallel query, or a reducer, I give up control over when, how often, and in what order it runs.

A pure function tolerates that loss of control better. By "pure," I mean a call that behaves like a calculation: when it returns normally, the same explicit inputs produce the same returned value, and the call leaves no externally visible effects behind. For an instance method, the receiver's observable state is part of that story too.

By "effect," I mean behavior beyond the returned value that depends on or changes the surrounding world: reading the clock, using current culture, writing a row, sending an email, mutating shared state, or calling the network.

An effectful function can still be correct when handed to another abstraction, but it needs another visible contract: idempotency, retry-safety, cache-safety, thread-safety, transactionality, or an explicit effect boundary.

The examples use C#-style syntax, but the point is broader. You do not need a new framework to write pure functions. You already use purity-like contracts whenever you sort, filter, cache, compare, aggregate, or parallelize.

## The function you hand over

In Part 1, a monad was useful because a context knew how to apply a function.

A list applies a function to many values. An option-like value may apply it zero or one times. A result-like value may skip it after failure.

In each case, I give some context a function, and the context controls the application.

This post is about the other side of that bargain:

```text
What kind of function am I safe to hand over?
```

If the function is value-like, the context has more freedom. It can call the function now, later, once, many times, lazily, or as part of a larger composition.

If the function is interaction-like, the context's strategy becomes observable. How many times it calls the function, when it calls it, whether it retries, whether it short-circuits, whether it runs in parallel - those details may now matter.

Purity is the contract that lets me stop caring about many details of that application. When the function has effects, those details come back.

## Number, timing, and order

Purity makes the number, timing, and order of calls less important. Effects make them part of the contract.

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

If `CalculateTotal` is a pure calculation, repeating it does not send another email, write another row, publish another event, or mutate caller-owned state. Retrying may still be useless if the failure is deterministic, but the repeat itself does not duplicate an external effect.

`ChargeCard` is different. It may call a payment processor, reserve funds, write a ledger entry, send a receipt, or publish an event. Repeat it and you may charge twice.

`ChargeCard` can still be a good boundary. The caller just needs a different contract. A payment operation can be safe to retry when it uses an idempotency key and the receiving system honors it. Here I am using idempotency in the distributed-systems sense: repeating the same logical request produces the same intended external state.

That is a useful pattern. It gives an effectful call one pure-like property: repetition becomes safer. It is still a larger contract because part of the guarantee now lives outside the method.

Purity still has limits. It does not make a calculation cheap, total, or well-named. It avoids hidden shared mutation, which makes parallelization simpler, but thread safety can still depend on immutable inputs and implementation details. Purity only removes hidden inputs and externally visible effects from the call's observable behavior.

## Types for values, purity for calls

Types make assumptions about values explicit. If I call `.Length`, add two values, or index into a collection, I am assuming those operations make sense.

Purity does something similar for calls. If I retry a method, cache its result, pass it to `Where`, run it in parallel, or move it earlier in a program, I am assuming something about the method's behavior.

From the caller's point of view, the composition rule is simple:

```text
value-like + value-like = value-like
value-like + interaction-like = interaction-like
```

A pure calculation can call another pure calculation and remain value-like.

Once it reads the clock, calls a service, writes telemetry, mutates shared state, or invokes an effectful callback, the composed method makes a different promise. That does not make it bad. It just means callers can no longer treat it as only a calculation.

## Delegating the call

Higher-order functions are not exotic. Most programmers do not say "higher-order function" when they sort a list, filter a collection, populate a cache, or run a parallel query. They pass comparers, predicates, selectors, factories, and accumulators.

The important part is that another piece of code now controls the call.

| API shape | Function handed over | What the abstraction controls |
| --- | --- | --- |
| `Sort(comparer)` | comparer | comparison count and order |
| `Where(predicate)` | predicate | evaluation timing and count |
| `Select(selector)` | projection | evaluation timing and count |
| `GetOrAdd(valueFactory)` | value factory | whether or how often to compute |
| `AsParallel().Select(...)` | projection | thread, order, and concurrency |
| `Aggregate(...)` | accumulator | grouping, partitioning, and order |

Most programmers call these sorting, filtering, caching, mapping, reducing, and looping. The shape is the same: I give behavior to another piece of code, and that piece of code decides how to invoke it.

Consider a value-like function:

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

Now compare an interaction-like version:

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

## Everyday places this already happens

Sorting is the oldest everyday example:

```csharp
customers.Sort((left, right) =>
    string.Compare(left.LastName, right.LastName, StringComparison.Ordinal));
```

The comparison needs to give consistent answers for the same inputs. If it reads the clock, consults mutable global state, or changes shared state that later comparisons depend on, sorting becomes harder to reason about because algorithm details become observable.

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

Cache factories are an especially good .NET example. `ConcurrentDictionary<TKey, TValue>.GetOrAdd` may call its value factory more than once under concurrency, even though only one value is stored:

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

Reducers follow the same pattern. Once an abstraction partitions or combines work, the accumulator may need additional contracts such as statelessness, an identity value, and associativity.

## The purity version of function color

Bob Nystrom's ["What Color is Your Function?"](https://journal.stuffwithstuff.com/2015/02/01/what-color-is-your-function/) is about async, but the useful shape is broader: a property of a function can stop being a local implementation detail and start affecting composition.

In his article, async affects how a function can be called. Here, effects affect what another abstraction is allowed to do with the function.

```text
Async changes call mechanics.
Effects change call assumptions.
```

A pure function can be applied more freely. An effectful function can still be correct, but the abstraction's call strategy becomes part of the behavior unless another contract makes that strategy safe.

## Hidden inputs become setup

Effects are not only writes. Hidden reads can also make a call depend on setup outside the visible arguments.

```csharp
string FormatAmount(decimal amount)
{
    return string.Format("{0:C}", amount);
}
```

This looks like:

```text
decimal -> string
```

but if it uses `CurrentCulture`, the real shape is closer to:

```text
decimal + current culture -> string
```

The hidden input does not disappear. It becomes setup: before calling `FormatAmount`, make sure the ambient culture is correct.

The same pattern appears with time:

```csharp
bool IsExpired(Subscription subscription)
{
    return subscription.ExpiresAt < DateTimeOffset.UtcNow;
}
```

The caller can still use this correctly by freezing the clock, injecting a clock service, or running under a known time boundary. But if the input becomes explicit:

```csharp
bool IsExpired(Subscription subscription, DateTimeOffset now)
{
    return subscription.ExpiresAt < now;
}
```

then the call no longer needs ambient setup to say what facts it is deciding over.

Making an input explicit does not remove complexity. It moves the complexity to the call boundary, where composition can see it:

```csharp
string FormatAmount(decimal amount, IFormatProvider culture)
bool IsExpired(Subscription subscription, DateTimeOffset now)
Money CalculateTotal(Order order, TaxRate taxRate, Discount discount)
```

Hidden inputs are useful when the method's job is to interact with the environment. They become expensive when the caller wants repeatability, replay, comparison, caching, or composition. In those cases, making the input explicit moves setup to the call boundary, where the composition can see it.

## Mutation and local effects

Purity is about observable behavior, not implementation style.

Purity is also not about copying everything or recomputing forever. A pure implementation can use local mutation, structural sharing, memoization, pooling, or other optimizations as long as the caller cannot observe hidden inputs or externally visible effects. Performance is still a real design constraint; purity does not make computation free.

Local mutation can be compatible with purity if it does not escape:

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

This is different:

```csharp
public static void AddItem(List<Item> items, Item item)
{
    items.Add(item);
}
```

That mutates caller-owned state. The relevant question is whether the caller can observe the mutation and must account for it.

## Boundaries and restraint

Functional core / imperative shell is one way to keep the functions I hand over value-like. It is a practical way to apply the thesis, not the thesis itself.

The shell is where I keep control of interaction-like calls. The core is where I keep value-like functions that can be reused, tested, batched, cached, retried, simulated, or passed to other abstractions with fewer surprises.

The shell interacts with the world. It reads the database, checks the clock, calls services, and writes results. The core receives values and returns values.

```text
CheckoutService:
    get tax rate
    get discount
    call CheckoutMath.CalculateTotal

CheckoutMath.CalculateTotal:
    Order + TaxRate + Discount -> Money
```

Gary Bernhardt popularized the phrase ["functional core, imperative shell"](https://www.destroyallsoftware.com/talks/boundaries). It works here because it turns environment into data and hidden setup into visible input.

```text
Use dependency injection at interaction boundaries.
Use explicit values in calculation-heavy code.
```

Constructor injection is appropriate for application services, repositories, adapters, clients, and orchestration code. Explicit method parameters are often better for domain policy, pricing, validation, authorization, scheduling, retry rules, and other code where the main job is to decide.

Effects belong where callers expect interaction with the world. Repositories should talk to databases. Controllers should orchestrate. Job handlers should sequence effects. Migration scripts should update state. In code like that, a procedural style is often the most honest representation of the work.

There is a tradeoff. Making behavior visible can make code more verbose. Passing `now`, `culture`, `taxRate`, or `discount` explicitly can be overkill. Expose the dependencies that materially affect correctness, repeatability, reuse, or caller obligations.

There is also a bad version of this idea:

```csharp
var a = Step1(input);
var b = Step2(a);
var c = Step3(b);
var d = Step4(c);
```

The pipeline shape can be fine. Passing the output of one pure function into the next is exactly how composition is supposed to work. Names like `CalculateTotal`, `DecideRenewal`, `ValidatePolicy`, and `PlanShipment` create useful boundaries. `Step1` through `Step4` usually tell the reader nothing.

Pure and effectful methods make different promises. A pure method is value-like. It is easier to hand to another piece of code because the number, timing, and order of calls matter less. An effectful method is interaction-like. It can still be the right design, but it needs a different contract: the effect should be obvious, explicit, isolated, or made safe by something like idempotency, transactionality, or synchronization.

The point is not to make every function pure. The point is to know what kind of function I am handing over.

Side effects belong in real programs. The useful discipline is knowing when a call is a calculation and when it is an interaction before the difference becomes a bug.
