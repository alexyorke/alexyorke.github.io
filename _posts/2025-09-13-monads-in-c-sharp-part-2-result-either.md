---
title: "Monads in C# (Part 2): Result (Either)"
date: 2025-09-13
description: "Build a small Result type in C# and use `Map`/`Bind`/`Match` to compose short-circuiting workflows with explicit errors."
---

**Previously in the series**: [List is a monad (part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/)

> _Note_: rewritten 2025-12-21.

In **Part 1** (`List`), we contrasted `Map` (`Select`) vs `Bind` (`SelectMany`) on `List<T>`, then built `Maybe<T>` for optional pipelines.

The Result monad lets you sequence computations that can fail. You return `Ok(value)` or `Fail(error)`, then compose with `Bind` to propagate the first failure (later steps don’t run; the failure just flows through).[^shortcircuit]
If you need to accumulate many errors (form validation) or you have more than two meaningful outcomes, `Result` is not a great fit. You _can_ model “many errors” as `Result<T, List<TError>>`, but then you have to define the aggregation rules yourself.

This post uses `Result<TSuccess, TError>` to model failure with an error value. It’s like `Maybe<T>`, except the “no value” case carries why it’s missing. Prefer to keep results in a Result and compose with `Bind`; handle them at boundaries **or when translating between layers** (mapping infrastructure errors to domain errors, adding context, logging, retry/fallback).[^checked-exceptions]

> **Note:** `Bind` still short-circuits. `Result<T, List<TError>>` doesn’t magically “accumulate”; accumulation requires a different, explicit combining/validation API.

If you're coming from FP, this corresponds to a right-biased `Either<TError, TSuccess>` (note the swapped type parameter order): `TError` is the failure branch and `TSuccess` is the success branch, by convention.

### TL;DR
What it looks like (`Error` is just one option):

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

Result<User, Error> result =                   // Result<User, Error>
    ParseId(inputIdFromRequest)                // Result<int, Error>, first in chain, always runs
        .Bind(id => FindUserOrFail(repo, id))  // Result<User, Error>, only runs if ParseId succeeded
        .Bind(DeactivateDecision);             // Result<User, Error>, only runs if FindUser succeeded

// Handle at the boundary (or when translating between layers):
string message = result.Match(
    ok:  _ => "User deactivated",
    err: e => $"Deactivate failed: {e.Code} - {e.Message}");
```

Missing the intermediate `var`s? Here are the types:

- `ParseId`: takes a `string`, returns `Result<int, Error>`
- `id => FindUserOrFail(repo, id)`: takes an `int`, returns `Result<User, Error>` (dependency injection via a lambda/closure)
- `DeactivateDecision`: takes a `User`, returns `Result<User, Error>`
- `Bind`: called on a `Result<T, Error>`, takes a function `Func<T, Result<U, Error>>`, returns `Result<U, Error>`

`Bind(FindUser)` == `Bind(id => FindUser(id))`: on success, `Bind` passes the inner value to the next step; on failure, it forwards the `Error`.

Both `Map` and `Bind` run a function **only on success** and propagate failures unchanged (but if your mapping/binding function throws, it still throws unless you catch/bridge it).

#### The problem: explicit vs. implicit

In C#, fallible work usually becomes either **implicit control flow** (`exceptions`) or **explicit checks** (guard clauses).

**Option A: Implicit Control Flow (Exceptions)**
Signatures might not show failure.[^checked-exceptions] `DeactivateUser` returns `void`, but it can throw while parsing/loading/saving, or due to business rules.

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
    if (inputId is null) throw new ArgumentNullException(nameof(inputId));

    int id;
    try
    {
        id = int.Parse(inputId);
    }
    catch (FormatException ex)
    {
        throw new InvalidOperationException("DeactivateUser failed at: parse id", ex);
    }
    catch (OverflowException ex)
    {
        throw new InvalidOperationException("DeactivateUser failed at: parse id", ex);
    }

    User? user;
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

In small snippets, throw sites are obvious. In larger apps, `exceptions` can originate far from where you want context, so you either rely on boundary handlers or add local `try/catch` for context/recovery.

**Main point: you’re responsible for `null` checks, catching, initializing the user variable outside try/catch, and stopping the pipeline on failure. It’s easy to repeat, noisy, and easy to get wrong.**

**Option B: Explicit Validation (Guard Clauses)**
To reserve `exceptions` for exceptional cases, you write guard clauses and early returns. It’s linear, but noisy.

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
    catch (Exception)
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
    catch (Exception)
    {
        return DeactivateUserResult.InfraError;
    }
    return DeactivateUserResult.Success;
}
```

> **Note:** `User` is **mutable** here to keep focus on `Result`. Prefer immutability in real domain code.[^immutability]

This enum doesn’t carry a *success payload* (only a status), so at this point you might reach for a tuple like `(bool Success, User? User, string Error)`.

The problem: tuples don’t enforce invariants. Nothing stops you from creating `Success = true` **and** `Error = "Failed"`. Or from ignoring `Success` and later dereferencing a `null` `User`. Ka-blam-oh.

> **Aside:** You can fix the “invalid combinations” problem with an `OperationStatus` hierarchy (e.g., `OperationSuccess` / `OperationFailure`) or a private constructor + `Success(...)`/`Failure(...)` factories. That helps, but you still need good composition to avoid “check the status after every step.”

`Result` packages these conventions + combinators into a familiar, reusable shape: a single return value that’s either `Ok(...)` or `Fail(...)`, plus standardized composition (`Map`/`Bind`). When you need other effects, you usually nest (e.g., `Task<Result<...>>`) and use helpers.

#### The solution: the Result monad

`Result` returns failure as data, not an `exception` jump. Expected failures stay on the return path (as long as your steps return `Result` rather than throwing); unexpected `exceptions` still escape. This teaching version does not automatically catch `exceptions`.

Now each step either produces the next value or stops with an `Error`.

LINQ query syntax, for those so inclined (like me). This requires `Select`/`SelectMany`; see the appendix:

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

> **Aside:** I'd encourage you to open your IDE and write a `Result` implementation without the use of AI. Think about its public API, then work backwards.

Teaching implementation (don’t ship it; use *LanguageExt* or *CSharpFunctionalExtensions*. *FluentResults* is another good option but models a different “reasons list” style `Result`).
This implementation is intentionally minimalist and **intentionally unsafe around `default`/null**: it stores a `default` in the unused slot (don’t read it), and real implementations either forbid nulls or make invalid access impossible/throwing.
If you ever add `Value`/`Error` getters, you must make invalid access impossible or throwing (e.g., `Value` on failure throws, `Error` on success throws; or model the union properly with a tagged union / separate types).

#### Where is the “Unit” / “Return” / “Pure” method?
In monad terms, **Unit** (also called **Return** or **Pure**) lifts a value into the monadic context. For the monad `Result<_, TError>`, that’s `Ok(...)`.
`Fail(...)` injects an error value; it’s not “Unit”.

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

Aside: in C#, `string?` is a nullable reference annotation (static analysis). In Rust, `?` is an early-return operator for `Result`/`Option`.

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
Avoid serializing `Result` in **public contracts**: it leaks an internal control-flow wrapper into your schema. Prefer `Match` into `DTO`s/status/`ProblemDetails` (unless you intentionally standardize an envelope or write a custom converter).

With the teaching `Result` type in this post (it only exposes `IsSuccess`/`IsFailure`), many serializers will emit only the flags — **meaning you lose the payload** — another reason not to serialize it.
(Property naming like `IsSuccess` vs `isSuccess` depends on serializer options.)

```json
{ "IsSuccess": true, "IsFailure": false }
```

Many real-world `Result` types expose `Value`/`Error` (and flags like `IsSuccess`) publicly, so serializers may emit the wrapper (or even throw if a getter throws on invalid access), e.g.:

```json
{
  "IsSuccess": true,
  "IsFailure": false,
  "Error": null,
  "Value": { "Id": 123, "IsActive": false }
}
```

Yikes. Now your contract includes success/failure flags plus internal error/value shapes. Unwrap with `Match` and return a real `DTO`/status/`ProblemDetails`.

### Why bother?
Why return `Result` instead of throwing or using enums?
*   **Explicit Signatures:** `Result<User, Error>` tells you up front that failure is on the table.
*   **Fewer sentinel values:** Avoid `-1` / `null` / “magic” return values used as control flow. (You still choose how to model errors: strings, enums, or typed errors.)
*   **Testability:** Tests can assert success/failure and inspect the specific error (`Code`, type, message) via `Match`/`IsSuccess`, without `try/catch` scaffolding.

### Where `Result` fits (and where it doesn’t)
Rule of thumb: use `T?` (or `Maybe<T>`) for expected absence (no reason needed). Use `Result<TSuccess, TError>` when you want a typed reason and fail-fast composition.
For reference types, `T?` is a static annotation, not a runtime guarantee.

`Result` fits **domain logic** (expected failures you handle). It doesn’t replace `exceptions`.[^always-valid]

1.  **Infrastructure:** Common approach: let infra throw and handle at boundaries (middleware/logging/global handlers). Alternative: catch/bridge infra exceptions into `Result` at the repo/client boundary for uniform “no-throw” composition.
2.  **Bugs:** Throw for programmer errors (null args, impossible states, broken invariants). Use `Result` for expected, user/domain-driven failures.
3.  **Accumulation:** `Bind` stops at the first `Error` (fail-fast). If you need to collect *all* validation errors, use a validation/combine API that accumulates errors instead of short-circuiting.

### Putting it together
#### Example: deactivate a user
We want to deactivate a user given an `id` from an HTTP request (received as a **string**, parsed to an `int`).[^id]

> **Note:** I’m using an HTTP API purely as a boundary example. `Result` isn’t “for HTTP”; it’s for any place you want explicit, composable success/failure (CLI commands, message handlers, background jobs, UI workflows, etc.).

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
        // Workflow composition; persistence happens at the boundary (see `HandleDeactivateRequest`).
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

Compute `Result<User, Error>` internally, then `Match` at the boundary (`HandleDeactivateRequest`) — or earlier if you’re translating between layers.
Note: this is not a purely mechanical “replace guard clauses with `Bind`” refactor. In Option A/B, `DeactivateUser` both decided *and* persisted; here, `DeactivateUser` computes the decision and the boundary persists. Don’t accidentally drop `_repo.Save(...)` when refactoring.

This example mutates `user.IsActive` to keep focus on the mechanics; prefer immutability in real domain code.[^immutability] Also beware partial state changes and aliasing: if you mutate in the middle of a longer chain and a later step fails, the in-memory object stays mutated — and if the object is shared/tracked (e.g., by an ORM), other code can observe the mutation even when the overall workflow fails.

#### Why is `_repo.Save(user)` inside `Match`?
`Save` is `I/O` and often fails via `exceptions` (DB/network outages, timeouts). Here we keep those **infrastructure failures** as `exceptions` handled at the boundary, and use `Result` for **expected domain failures** (invalid ID, not found, already inactive). Note that `FindUser` is also `I/O`: it models “not found” as `Fail`, but unexpected repo exceptions still escape unless you catch/bridge them.
### Async: the `Task<Result<...>>` nesting weirdness

Async often gives you `Task<Result<T, Error>>` (I/O). Parsing an ID is usually CPU work, so keep `ParseId` synchronous; then `await` the I/O step and continue with `Bind`. With the teaching `Result` type in this post, one simple way to bridge `Result<T, E>` into `Task<Result<U, E>>` is `Match`.

```csharp
// Assume: Task<Result<User, Error>> FindUserAsync(int id)
public Task<Result<User, Error>> DeactivateUserAsync(string inputId) =>
    ParseId(inputId).Match(
        ok: async id =>
        {
            Result<User, Error> user = await FindUserAsync(id);
            return user.Bind(DeactivateDecision);
        },
        err: e => Task.FromResult(Result<User, Error>.Fail(e)));
```

If you want fluent pipelines, use a library with async `Map`/`Bind` overloads/extensions for `Task<Result<...>>`. This is library-specific: you’re relying on extension methods that lift `Bind` across `Task`.

- **[CSharpFunctionalExtensions](https://github.com/vkhorikov/CSharpFunctionalExtensions)**
- **[LanguageExt](https://github.com/louthy/language-ext)**

```csharp
// Requires library-provided async `Bind` extensions for `Task<Result<...>>`:
public Task<Result<User, Error>> DeactivateUserAsync(string inputId) =>
    Task.FromResult(ParseId(inputId))
        .Bind(FindUserAsync)
        .Bind(user => Task.FromResult(DeactivateDecision(user)));
```

### Recap

`Result` keeps “expected failure” in-band, as data.

1.  **Chain** with `Map`/`Bind` (the universal monad pattern).
2.  **Handle** `Task<Result<...>>` using async extensions to fuse the effects.
3.  **Decide** once at the edge with `Match`.

Toolbox recap: `List` (many), `Maybe` (optional), `Result` (success/failure with a reason). Same core shape: `Bind`/`SelectMany`.

### Appendix: LINQ query syntax (`Select`/`SelectMany`)
If you want the simple `from`/`from`/`select` query syntax to compile, add these extension methods (or add the same methods directly to `Result`). (Other query keywords like `where` require additional methods.)

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

[^id]: In real systems, prefer a strongly typed ID (e.g., `UserId`) over primitives. Here I keep it simple: `string` at the boundary, parse to `int`, focus on `Result`.
[^checked-exceptions]: Java has *checked exceptions* (`throws` forces callers to catch/declare them), but unchecked exceptions still exist. C# has no checked exceptions, so “might throw” usually isn’t in the signature (unless documented).
[^immutability]: Mutation makes pipelines harder to reason about and test. Prefer immutability (`record` + `init`, or return a new value); I mutate here to keep focus on `Result` mechanics.
[^always-valid]: Vladimir Khorikov, [Always valid vs not always valid domain model](https://enterprisecraftsmanship.com/posts/always-valid-vs-not-always-valid-domain-model/).
[^unused-result]: C# lets you ignore return values, so a `Result` can be silently dropped. Use a Roslyn analyzer to flag unused `Result`s.
[^shortcircuit]: “Short-circuit” here: after the first failure, later steps aren’t called; the failure value just propagates.
