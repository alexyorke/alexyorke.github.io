---
title: "What Kind of Function Can I Hand Over?"
date: 2026-06-13
description: "Effectful functions depend on hidden world-state. That is why they are easier to reason about at the edge."
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/), [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result/)

In the first two parts, the focus was on `List<T>`, `Maybe<T>`, and `Result<TSuccess, TError>`.

Those types are interesting because they do more than hold values. They also decide how the next function is called.

With `List<T>`, the next function may run once per element. With `Maybe<T>`, it may not run at all. With `Result<TSuccess, TError>`, it may only run if the previous step succeeded.

So when we call `Map`, `Bind`, or `SelectMany`, we are handing a function to another piece of code and letting it decide part of the execution.

That raises the question in this article's title:

> What kind of function can I hand over?

The answer depends less on the delegate type and more on what the function needs in order to run correctly.

Some functions only need their explicit arguments. Other functions also need the current time, a database row, a file, a feature flag, a cache entry, a transaction, a network response, a mutable field, or some other part of the outside world.

That difference is the rationale behind functional core / imperative shell.

Programs need to read files, call services, write rows, send messages, and observe time. The reason to push effects toward the edge is simpler: effectful functions depend on surrounding context that is not visible in the function's ordinary input list. The deeper those functions live inside a program, the more of that hidden context the caller has to reconstruct.

A pure function is easy to hand over because it carries less hidden context with it.

An effectful function can still be handed over, but now the receiver must respect more rules.

## Two shapes of function

For this article, a pure function is one where the call can be replaced by a lookup from explicit inputs to return values without changing the program's observable behavior.

This is a practical, code-review definition.

This function has everything it needs in the parameter list:

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

Give it the same `Order`, `TaxRate`, and `Discount`, and it returns the same `Money`. It does not read from the clock, check a feature flag, query a repository, mutate shared state, send an email, or write an audit row.

It has this shape:

```text
Input -> Output
```

An effectful function has a different shape. It may still have ordinary parameters, but it also reads from or writes to something outside those parameters.

```csharp
public Money CalculateTotal(Order order)
{
    var taxRate = _taxService.GetRate(order.ShippingAddress);

    _audit.Record($"Calculated total for {order.Id}");

    return order.Subtotal.ApplyTax(taxRate);
}
```

The signature looks like this:

```text
Order -> Money
```

But the behavior is closer to this:

```text
Order + World -> Money + World'
```

The word `World` is just a model. It stands for whatever surrounding state the function observes or changes: current time, current configuration, database contents, remote service behavior, cache state, log state, thread scheduling, transaction state, and so on.

You do not literally pass a `World` object in ordinary C#.

The point is that effectful functions have hidden inputs and sometimes hidden outputs. They read facts that are not in the parameter list, and they may change facts that later code can observe.

That is what I mean by an effect.

Here, an effect means that running the function depends on, or changes, something outside the explicit arguments and return value.

## Hidden inputs are still inputs

Suppose this calculation depends on the current tax rate.

```csharp
public Money CalculateTotal(Order order)
{
    var taxRate = _taxService.GetRate(order.ShippingAddress);

    return order.Subtotal.ApplyTax(taxRate);
}
```

Dependency injection may make `_taxService` visible at the object boundary:

```csharp
public PricingService(ITaxService taxService)
```

That is useful. It tells us where the service may get tax information.

But it does not tell us which tax rate was used for this call.

The dependency is the source. The fact is the value that came back.

Those are different things.

If the pricing rule is the important part, this version has a clearer boundary:

```csharp
public static Money CalculateTotal(Order order, TaxRate taxRate)
{
    return order.Subtotal.ApplyTax(taxRate);
}
```

The application can still observe the world:

```csharp
var taxRate = _taxService.GetRate(order.ShippingAddress);
var total = Pricing.CalculateTotal(order, taxRate);
```

The effect has not disappeared. The tax service still exists. The program still needs a boundary where it asks the outside world for a tax rate.

But the decision now receives an ordinary value.

That distinction matters because "whatever the provider returns now" is a different contract from "calculate using this observed tax rate."

The first contract depends on call time, provider state, cache freshness, network behavior, and possibly transaction state. The second contract depends on a value already in hand.

This is why passing `IClock` into a policy is different from passing `Instant now`.

```csharp
var now = _clock.UtcNow;
var expired = SubscriptionPolicy.IsExpired(subscription, now);
```

The shell observes time. The policy receives a fact.

Likewise:

```csharp
var config = LoadConfiguration();
var delay = RetryPolicy.CalculateDelay(attempt, config.Backoff);
```

The shell reads configuration. The policy receives values.

This tradeoff is not always worth making. Passing every observed value through every layer can make code noisy. Sometimes "ask the provider at the point of use" is the right contract.

But when a decision needs to be tested, replayed, audited, cached, compared, simulated, batched, or handed to another function, the observed facts usually deserve to be explicit.

## Effects make ordering part of the contract

A hidden input is already enough to make a function more situated. A hidden output makes the problem sharper.

Two effectful steps can depend on each other without passing an ordinary value.

One method writes a row. Another method reads it later. One method reloads configuration. Another method uses whatever configuration is current. One method opens a transaction. Another method assumes it is running inside that transaction. One method publishes an event. Another method assumes the database commit has already happened.

There is real dataflow, but it is not visible in the function signature.

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

The call site says:

```csharp
pricing.CalculateTotal(order);
```

But the real behavior depends on more than `order`.

Was the configuration loaded? Which version was loaded? Could another thread reload it during this call? What happens if reload fails halfway? Is the discount supposed to come from the same snapshot as the tax rate?

None of those questions are exotic. They are ordinary questions in ordinary programs.

The issue is that the function's apparent shape is smaller than its real shape.

When effectful operations are buried deep inside a codebase, the programmer has to remember the invisible preconditions around them:

```text
configuration must already be loaded
this must run inside a transaction
this must not run twice
this must run after validation
this must run before publishing the event
this must observe the same snapshot as the previous read
this must not run in parallel
```

Those requirements may be correct, but they restrict where the function can be called.

They also restrict who can safely call it.

A value-like function is easier to move because the caller only has to supply values. An effectful function may require the caller to arrange a piece of the world first.

## Effects propagate

Effects also propagate through composition.

If a function calls an effectful function, the combined function is effectful too.

```csharp
public Money CalculateTotalForCheckout(Order order)
{
    var taxRate = _taxService.GetRate(order.ShippingAddress);

    return Pricing.CalculateTotal(order, taxRate);
}
```

`Pricing.CalculateTotal` may be pure. The wrapper is effectful too because it reads from `_taxService`.

The same is true in the other direction:

```csharp
var message = RenderReceipt(order, total);

_emailGateway.Send(message);
```

`RenderReceipt` may be a pure formatter. The workflow is still effectful because it sends an email.

This is simply how effects compose.

The important consequence is that effects tend to move outward through the call graph. Once an operation reads or writes the world, every larger operation that depends on it must account for that fact.

If the effect sits near the edge, that propagation is contained. The boundary code is already responsible for sequencing, retries, transactions, logging, errors, and communication with the outside world.

If the effect sits in the middle of a rule, predicate, formatter, or state transition, then the middle of the program starts to inherit those concerns too.

That is the practical argument for functional core / imperative shell.

The point is more practical than moral: the shell is where world-management already belongs.

## The handoff problem

Now return to the original question: what kind of function can I hand over?

A higher-order API does not just receive a function. It receives permission to call that function according to its own rules.

A collection may call a selector once per element.

```csharp
var totals = orders.Select(order =>
    Pricing.CalculateTotal(order, taxRate, discount));
```

A `Maybe<T>` may skip the function completely.

```csharp
var total = maybeOrder.Map(order =>
    Pricing.CalculateTotal(order, taxRate, discount));
```

A `Result<TSuccess, TError>` may only call the function after success.

```csharp
var total = validatedOrder.Bind(order =>
    CalculateTotalResult(order, taxRate, discount));
```

A retry helper may call an operation more than once.

```csharp
var total = Retry(() =>
    Pricing.CalculateTotal(order, taxRate, discount));
```

These are different execution strategies.

A value-like function tolerates many of them. If it runs twice, we spend extra CPU. If it runs later, it still sees the same explicit facts. If it is skipped, no email is lost. If it runs inside a larger composition, it does not quietly change some shared state that the caller forgot about.

An effectful function behaves differently.

```csharp
var total = Retry(() =>
    _pricingService.CalculateTotal(order));
```

That may read a different tax rate on the second attempt. It may write two audit rows. It may depend on whether configuration was reloaded between attempts. It may require a transaction that the retry helper does not know about.

The delegate type does not show any of that.

```csharp
Func<Money>
```

Both versions fit behind the same type. But one is much easier to delegate.

This is the real issue with effectful callbacks. The callback may be shaped like a calculation while behaving like a situated operation.

Once another API controls when, whether, how often, or where the function runs, hidden context becomes part of the API contract.

Effectful callbacks are still useful in the right places. Event handlers, message consumers, database transaction blocks, and request handlers are deliberately effectful.

Those APIs should make that contract obvious, because the callback is part of boundary work.

## Why the edge helps

Moving effects to the edge gives the program a place to control the world before handing values inward.

The shell can decide:

```text
when to read
which transaction to use
which snapshot to observe
which idempotency key to attach
how to retry
what to log
what to publish
how to handle failure
whether to commit or roll back
```

The core can then decide with values:

```csharp
public static RenewalDecision Decide(
    Subscription subscription,
    PaymentStatus paymentStatus,
    Plan plan,
    Instant now)
{
    if (paymentStatus.IsDelinquent)
    {
        return RenewalDecision.DoNotRenew("Payment is delinquent");
    }

    if (subscription.ExpiresAt <= now)
    {
        return RenewalDecision.Renew(plan.RenewalPrice);
    }

    return RenewalDecision.NoActionRequired();
}
```

The application service remains effectful:

```csharp
public RenewalDecision DecideRenewal(Subscription subscription)
{
    var now = _clock.UtcNow;
    var paymentStatus = _payments.GetStatus(subscription.CustomerId);
    var plan = _plans.GetPlan(subscription.PlanId);

    return RenewalPolicy.Decide(
        subscription,
        paymentStatus,
        plan,
        now);
}
```

The effectful code is still present. The difference is that the important decision can be tested, replayed, compared, cached, explained, or run in a batch without recreating the world that originally produced the facts.

That is the benefit.

The core does not need to know whether `PaymentStatus` came from a database, an HTTP call, a cache, a fixture, a message, or a simulation. It only needs the fact.

The shell owns the question "where did this fact come from?"

The core owns the question "what follows from these facts?"

That separation is the point of functional core / imperative shell.

## Local mutation and observable effects

This argument is about observable effects and caller-visible behavior more than whether the implementation uses assignment.

A function can use local mutation and still behave like a value-like function:

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

The builder is mutated, but the mutation is local. The caller observes only the returned value.

This is different:

```csharp
public static void AddItem(List<Item> items, Item item)
{
    items.Add(item);
}
```

That mutates caller-owned state. Later code can observe the change, so ordering now matters.

The important question is whether the caller has to account for something outside the explicit arguments and return value.

If yes, the function is carrying context.

## The rule

Effectful functions belong near the edge because the edge is where the program already has to manage the world.

That is where sequencing, retries, transactions, idempotency, logging, failure handling, and communication with external systems are easiest to see.

The deeper an effectful function is buried, the more hidden context travels with it. The caller may need to know what ran before, what state was prepared, what must not be repeated, what must be rolled back, and what other code may observe.

That makes the function harder to reuse and harder to hand over.

A value-like function can still be slow, partial, complicated, or wrong. And making every fact explicit can make simple code harder to read.

But when the code represents a decision, rule, predicate, formatter, state transition, or calculation that you want to compose freely, it is usually worth moving reads and writes outward.

Observe the world at the boundary.

Turn observations into values.

Pass those values into the core.

Then perform the resulting effects at the boundary again.

That is the functional core / imperative shell pattern in ordinary terms. It gives the program a controlled place to touch the world, and it gives the rest of the code functions that are easier to test, compose, replay, cache, batch, and hand over.
