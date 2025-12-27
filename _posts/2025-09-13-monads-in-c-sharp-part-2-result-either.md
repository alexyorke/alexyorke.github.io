---
title: "Monads in C# (Part 2): Result (Either)"
date: 2025-09-13
description: "Build a small Result type in C# and use `Map`/`Bind`/`Match` to compose short-circuiting workflows with explicit errors."
---

**Previously in the series**: [List is a monad (part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/)

> _Note_: rewritten 2025-12-21.

In **Part 1** (`List`), we contrasted `Map` (`Select`) vs `Bind` (`SelectMany`) on `List<T>` and then built `Maybe<T>` for optional pipelines.

The Result monad lets you sequence computations that can fail. You return `Ok(value)` or `Fail(error)`, then compose with `Bind` to short-circuit on the first failure. If you need to accumulate many errors (form validation) or you have more than two meaningful outcomes, Result is not a great fit.

This post uses Result<TSuccess, TError> to model failure with an error value. You can think of it as Maybe<T>, except the “no value” case carries why it’s missing. Keep results unwrapped until the boundary, then handle them with Match once.[^checked-exceptions]

If you're coming from FP, this is _essentially_ a right-biased `Either<TError, TSuccess>`: `TError` is the failure branch and `TSuccess` is the success branch, by convention.

### TL;DR
What it looks like (this `Error` record is just one option):

```csharp
public record Error(string Code, string Message);

// Creating results:
Result<User, Error> okUser = Result<User, Error>.Ok(user);
Result<User, Error> failed = Result<User, Error>.Fail(new Error("NotFound", "User not found"));

// Returning a Result from a function:
Result<User, Error> FindUserOrFail(IUserRepo repo, int id)
{
    User? user = repo.Find(id);
    return user is null
        ? Result<User, Error>.Fail(new Error("NotFound", $"User {id} not found"))
        : Result<User, Error>.Ok(user);
}

Result<User, Error> result =          // Result<User, Error>
    ParseId(inputIdFromRequest)                  // Result<int, Error>, first in chain, always runs
        .Bind(FindUser)               // Result<User, Error>, FindUser only runs if ParseId succeeded
        .Bind(DeactivateDecision);    // Result<User, Error>, DeactivateDecision only runs if FindUser succeeded

// Unwrap once at the boundary:
string message = result.Match(
    ok:  _ => "User deactivated",
    err: e => $"Deactivate failed: {e.Code} - {e.Message}");
```

Missing the intermediate `var`s? Here are the types:

- `ParseId`: takes a `string`, returns `Result<int, Error>`
- `FindUser`: takes an `int`, returns `Result<User, Error>`
- `DeactivateDecision`: takes a `User`, returns `Result<User, Error>`
- `Bind`: called on a `Result<T, Error>`, takes a function `Func<T, Result<U, Error>>`, returns `Result<U, Error>`

`Bind(FindUser)` == `Bind(id => FindUser(id))`: on success, `Bind` passes the inner value to the next step; on failure, it forwards the `Error`.

#### The problem: explicit vs. implicit

In C#, fallible work usually becomes either **implicit control flow** (`exceptions`) or **explicit checks** (guard clauses).

**Option A: Implicit Control Flow (Exceptions)**
Signatures might not show failure.[^checked-exceptions] `DeactivateUser` returns `void`, but it can throw while parsing/loading, or later via `null` dereferences and business rules.

```csharp
// The implicit "User" entity used in the examples below
public class User
{
    public int Id { get; set; }
    public bool IsActive { get; set; }
}
```

```csharp
private readonly IUserRepo _repo;

public void DeactivateUser(string inputId)
{
    int id;
    try
    {
        id = int.Parse(inputId);
    }
    catch (Exception ex)
    {
        throw new InvalidOperationException("DeactivateUser failed at: parse id", ex);
    }

    User user;
    try
    {
        user = _repo.Find(id);
    }
    catch (Exception ex)
    {
        throw new InvalidOperationException("DeactivateUser failed at: load user", ex);
    }

    if (user is null)
        throw new InvalidOperationException("User not found");

    if (!user.IsActive)
        throw new InvalidOperationException("User already inactive");

    user.IsActive = false;
    try
    {
        _repo.Save(user);
    }
    catch (Exception ex)
    {
        throw new InvalidOperationException("DeactivateUser failed at: save user", ex);
    }
}
```

In small code snippets like this one, throw sites are obvious. In larger apps, `exceptions` can originate far from where you want context, so you either rely on boundary handlers or add some local `try/catch` for context/recovery.

**Main point: you’re responsible for `null` checks, catching, and stopping the pipeline on failure. It’s easy to repeat, noisy, and easy to get wrong.**

**Option B: Explicit Validation (Guard Clauses)**
To reserve `exceptions` for exceptional cases, you write guard clauses and early returns. It’s linear, but noisy. Basically defensive coding.

```csharp
private readonly IUserRepo _repo;

public enum DeactivateUserResult
{
    Success,
    InvalidId,
    NotFound,
    AlreadyInactive,
    InfraError
}

public DeactivateUserResult DeactivateUser(string inputId)
{
    if (!int.TryParse(inputId, out var id)) return DeactivateUserResult.InvalidId;

    User? user;
    try
    {
        user = _repo.Find(id);
    }
    catch
    {
        return DeactivateUserResult.InfraError;
    }
    if (user is null) return DeactivateUserResult.NotFound;

    if (!user.IsActive) return DeactivateUserResult.AlreadyInactive;

    user.IsActive = false;
    try
    {
        _repo.Save(user);
    }
    catch
    {
        return DeactivateUserResult.InfraError;
    }
    return DeactivateUserResult.Success;
}
```

> **Note:** `User` is **mutable** here to keep focus on `Result`. Prefer immutability in real domain code.[^immutability]

This enum doesn’t carry a *success payload* (only a status), so at this point you might reach for a tuple like `(bool Success, User? User, string Error)`.

The problem: tuples don’t enforce invariants. Nothing stops you from creating `Success = true` **and** `Error = "Failed"`. Or from ignoring `Success` and later dereferencing a `null` `User`. Ka-blam-oh.

So you think: fine, don’t let people construct arbitrary combinations. Make a small status type with a private constructor and two factories: `Success(...)` and `Failure(...)` (or `OperationSuccess` / `OperationFailure`). That works, but you still need good composition to avoid “check the status after every step.”

That’s what `Result` buys you: a single return value that’s either `Ok(...)` or `Fail(...)`, plus standardized composition (`Map`/`Bind`). And when you need to combine it with other effects, you usually nest (e.g., `Task<Result<...>>`) and use dedicated helpers.

#### The solution: the Result monad

`Result` returns failure as data, not an `exception` jump. Expected failures stay on the return path (as long as your steps return `Result` rather than throwing); unexpected `exceptions` still escape. This teaching version does not automatically catch `exceptions`.

Now each step either produces the next value or stops with an `Error`.

LINQ query syntax, for those so inclined (like me). This requires `Select`/`SelectMany` helpers; see the appendix:

```csharp
Result<User, Error> result =
    from id in ParseId(inputId)
    from user in FindUser(id)
    from deactivated in DeactivateDecision(user)
    select deactivated;
```

If you find `Bind(FindUser)` hard to read, expand the method group into a lambda so you can “see the variable”:
`ParseId(inputId).Bind(id => FindUser(id))`.

### A tiny `Result` implementation
Teaching implementation (don’t ship it; use a library like *LanguageExt*, *CSharpFunctionalExtensions*, or *FluentResults*). Assumes you don’t call `Ok(null)` / `Fail(null)` and uses `default` for the unused slot.

#### Where is the “Unit” / “Return” / “Pure” method?
In monad terms, **Unit** (also called **Return** or **Pure**) lifts a value into the monadic context. For this `Result`, that’s `Ok(...)`:

`Fail(...)` is the other constructor, but it’s not “Unit”; it injects an error value instead of a success value.

Here's the code for Result:

```csharp
public sealed class Result<TSuccess, TError>
{
    private readonly TSuccess _value;
    private readonly TError _error;

    public bool IsSuccess { get; }
    public bool IsFailure => !IsSuccess;

    private Result(TSuccess value, TError error, bool isSuccess)
    {
        IsSuccess = isSuccess;
        _value = value;
        _error = error;
    }

    public static Result<TSuccess, TError> Ok(TSuccess value)
    {
        return new Result<TSuccess, TError>(
            value,
            default,
            true);
    }

    public static Result<TSuccess, TError> Fail(TError error)
    {
        return new Result<TSuccess, TError>(
            default,
            error,
            false);
    }

    public Result<U, TError> Map<U>(Func<TSuccess, U> f)
    {
        if (IsSuccess)
        {
            return Result<U, TError>.Ok(f(_value!));
        }

        return Result<U, TError>.Fail(_error!);
    }

    public Result<U, TError> Bind<U>(Func<TSuccess, Result<U, TError>> f)
    {
        if (IsSuccess)
        {
            return f(_value!);
        }

        return Result<U, TError>.Fail(_error!);
    }

    public TResult Match<TResult>(Func<TSuccess, TResult> ok, Func<TError, TResult> err)
    {
        if (IsSuccess)
        {
            return ok(_value!);
        }

        return err(_error!);
    }
}
```

Aside: in C#, `string?` is a nullable annotation (static analysis), not Rust’s `?` operator.

I'd encourage you to open your IDE and write a `Result` implementation without the use of AI. Think about its public API, then work backwards.

### Unwrap at the boundary
> **Boundary:** validate inputs, run domain logic, then `Match` into a public output (`DTO`s/status/`ProblemDetails`).
> Don’t ignore returned `Result`s; use an analyzer.[^unused-result]

```csharp
Result<int, string> result = Result<int, string>.Ok(42);

string output = result.Match(
    ok:  value => $"Success: {value}",
    err: error => $"Error: {error}"
);
```

#### Why you shouldn’t serialize `Result`
Don’t serialize `Result`: it leaks internal shape into your public contract. `Match` into `DTO`s/status/`ProblemDetails`.

Important nuance: the teaching `Result` type in this post only exposes `IsSuccess`/`IsFailure` publicly, so a default JSON serializer will typically emit only those flags (not the value/error payload).

```json
{ "isSuccess": true, "isFailure": false }
```

Many real-world `Result` types expose `Value`/`Error` (and flags like `IsSuccess`) publicly, so serializers emit the wrapper, e.g.:

```json
{
  "isSuccess": true,
  "isFailure": false,
  "error": null,
  "value": { "id": 123, "isActive": false }
}
```

Yikes. Now your contract includes `isSuccess`/`isFailure` plus internal error/value shapes. Unwrap with `Match` and return a real `DTO`/status/`ProblemDetails`.

### Why bother?
Why return `Result` instead of throwing or using enums?
*   **Explicit Signatures:** `Result<User, Error>` tells you up front that failure is on the table.
*   **Fewer ad-hoc conventions:** No `-1`, no magic strings, no `null` as an error signal.
*   **Testability:** Tests can assert success/failure and inspect the specific error (`Code`, type, message) via `Match`/`IsSuccess`, without `try/catch` scaffolding.

### Where `Result` fits (and where it doesn’t)
Rule of thumb: use nullable types/annotations (`T?`) for “may be null/missing”; use `Result<TSuccess, TError>` for “this operation can fail with a reason.”

`Result` fits **domain logic** (expected failures you handle). It doesn’t replace `exceptions`.[^always-valid]

1.  **Infrastructure:** For technical failures (DB/network outages, timeouts, unexpected `I/O` errors), `exceptions` handled at the boundary (middleware/logging/global handlers) are often a good fit.
2.  **Bugs:** Violated preconditions are programmer errors; throw (`ArgumentNullException`, `ArgumentException`, etc.) rather than returning a domain `Result`.
3.  **Accumulation:** `Bind` stops at the first `Error`. If you need to collect *all* validation errors, use a validation type that accumulates errors instead of short-circuiting.

> **Note:** `Result` short-circuits on the first `Error`. For “collect all errors” validation, use an accumulating validation type (often applicative / `Validated`-style), but we haven't really covered that yet.

### Putting it together
#### Example: deactivate a user
We want to deactivate a user given an `id` from an HTTP request (received as a **string**, parsed to an `int`).[^id]

> **Note:** I’m using an HTTP API purely as a boundary example. `Result` isn’t “for HTTP” — it’s for any place you want explicit, composable success/failure (CLI commands, message handlers, background jobs, UI workflows, etc.).

We'll use the same `Error` payload from earlier (this is **not** part of `Result` itself).

```csharp
public class User
{
    public int Id { get; set; }
    public bool IsActive { get; set; }
}

public sealed class UserService
{
    private readonly IUserRepo _repo;
    public UserService(IUserRepo repo)
    {
        _repo = repo;
    }

    public Result<User, Error> DeactivateUser(string inputId)
    {
        // Domain decision only; persistence happens at the boundary (see `HandleDeactivateRequest`).
        return ParseId(inputId)
            .Bind(FindUser)
            .Bind(DeactivateDecision);
    }

    public string HandleDeactivateRequest(string inputId)
    {
        Result<User, Error> result = DeactivateUser(inputId);

        return result.Match(
            ok: user =>
            {
                _repo.Save(user);
                return "User deactivated";
            },
            err: e => $"Deactivate failed: {e.Code} - {e.Message}");
    }

    private static Result<int, Error> ParseId(string inputId) =>
        int.TryParse(inputId, out var id)
            ? Result<int, Error>.Ok(id)
            : Result<int, Error>.Fail(new Error("Parse", "Invalid ID format"));

    private Result<User, Error> FindUser(int id)
    {
        var user = _repo.Find(id);
        return user is null
            ? Result<User, Error>.Fail(new Error("NotFound", $"User {id} not found"))
            : Result<User, Error>.Ok(user);
    }

    private static Result<User, Error> DeactivateDecision(User user)
    {
        if (!user.IsActive)
            return Result<User, Error>.Fail(new Error("Domain", "User is already inactive"));

        user.IsActive = false;
        return Result<User, Error>.Ok(user);
    }
}
```

Compute `Result<User, Error>` internally, then `Match` once at the boundary (`HandleDeactivateRequest`).
Note: this is not a purely mechanical “replace guard clauses with `Bind`” refactor. In Option A/B, `DeactivateUser` both decided *and* persisted; here, `DeactivateUser` computes the decision and the boundary performs persistence. Don’t accidentally drop `_repo.Save(...)` when refactoring.

This example mutates `user.IsActive` to keep focus on the mechanics; prefer immutability in real domain code.[^immutability] Also beware partial state changes: if you mutate in the middle of a longer chain and a later step fails, the in-memory object stays mutated.

#### Why is `_repo.Save(user)` inside `Match`?
`Save` is `I/O` and often fails via `exceptions` (DB/network outages, timeouts). Here we keep those **infrastructure failures** as `exceptions` handled at the boundary, and use `Result` for **expected domain failures** (invalid ID, not found, already inactive). Note that `FindUser` is also `I/O`; in this example it models “not found” as `Fail`, but unexpected repo exceptions still escape unless you catch/bridge them.
### Async: the `Task<Result<...>>` nesting weirdness

Async often gives you `Task<Result<T, Error>>`. With the teaching `Result` type in this post, you can’t call `.Bind(...)` on a `Task` without writing async helpers. The simplest version is: `await`, then `Bind`.

```csharp
public async Task<Result<User, Error>> DeactivateUserAsync(string inputId)
{
    Result<int, Error> id = await ParseIdAsync(inputId);
    return id.Bind(FindUser).Bind(DeactivateDecision);
}
```

If you want fluent pipelines, use a library with async `Map`/`Bind` overloads/extensions for `Task<Result<...>>`, e.g.:

- **[CSharpFunctionalExtensions](https://github.com/vkhorikov/CSharpFunctionalExtensions)**
- **[LanguageExt](https://github.com/louthy/language-ext)**

```csharp
// Requires library-provided async `Bind` extensions for `Task<Result<...>>`:
public Task<Result<User, Error>> DeactivateUserAsync(string inputId) =>
    ParseIdAsync(inputId)
        .Bind(FindUserAsync)
        .Bind(user => Task.FromResult(DeactivateDecision(user)));
```

### Recap

`Result` keeps “expected failure” in-band, as data.

1.  **Chain** with `Map`/`Bind` (the universal monad pattern).
2.  **Handle** `Task<Result<...>>` using async extensions to fuse the effects.
3.  **Decide** once at the edge with `Match`.

Toolbox recap: `List` (many), `Maybe` (optional), `Result` (failure). Same core shape: `Bind`/`SelectMany`.

### Appendix: LINQ query syntax (`Select`/`SelectMany`)
If you want the `from`/`select` query syntax to compile, add these extension methods (or add the same methods directly to `Result`):

```csharp
public static class ResultLinqExtensions
{
    // Required for `select`
    public static Result<U, TError> Select<TSuccess, U, TError>(
        this Result<TSuccess, TError> result,
        Func<TSuccess, U> selector) =>
        result.Map(selector);

    // Required for multiple `from` clauses
    public static Result<V, TError> SelectMany<TSuccess, U, V, TError>(
        this Result<TSuccess, TError> result,
        Func<TSuccess, Result<U, TError>> bind,
        Func<TSuccess, U, V> project) =>
        result.Bind(val => bind(val).Map(next => project(val, next)));
}
```

**Next in the series**: [Monads in C# (Part 3): The Reader Monad](https://alexyorke.github.io/2025/12/20/monads-in-c-sharp-part-3-the-reader-monad/)

[^id]: In real systems, use a Strongly Typed ID (e.g., `UserId`) rather than a bare number to avoid "Primitive Obsession." This post uses `string` at the boundary and parses to `int` to keep the example focused on `Result` composition.
[^checked-exceptions]: Java has *checked exceptions*: methods can declare them with a `throws` clause and callers must catch/declare them. Unchecked exceptions (`RuntimeException`, `Error`, subclasses) still aren’t reflected in signatures. C# has no checked exceptions, so “what might throw” usually isn’t visible in the method signature unless it’s documented (e.g., XML `<exception>` docs).
[^immutability]: Mutating domain objects makes pipelines harder to reason about and test. Prefer immutability (e.g., `record`s with `init`-only properties, or returning a new value) where you can; this post sticks to mutation to keep the focus on `Result` composition.
[^out-var]: C# supports inline `out` variable declarations (C# 7): e.g., `if (int.TryParse(input, out var id)) { ... }`. This makes a single `Try...` step fairly composable inside an `if`, but it doesn’t scale to multi-step pipelines the way `Result` + `Bind` does.
[^always-valid]: Vladimir Khorikov, [Always valid vs not always valid domain model](https://enterprisecraftsmanship.com/posts/always-valid-vs-not-always-valid-domain-model/).
[^unused-result]: C# lets you ignore return values, so a `Result` can be dropped. Use a Roslyn analyzer to flag unused `Result`s.
