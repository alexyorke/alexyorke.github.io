---
title: "Monads in C# (Part 2): Result"
date: 2025-09-13
description: "Build a small Result type in C# and use `Map`/`Bind`/`Match` to compose short-circuiting workflows with explicit errors."
---

**Previously in the series**: [List is a monad (part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/)

> _Note_: rewritten 2025-12-28.

In **Part 1** (`List`), we contrasted `Map` (`Select`) vs `Bind` (`SelectMany`) on `List<T>`, then built `Maybe<T>`.

If you read Part 1, you already know the shape: `Bind`/`SelectMany` chains steps, and `Maybe` decides whether the next step runs.

The `Result` monad[^result-monad-precise] lets you compose computations that can fail. You return `Ok(value)` or `Fail(error)`, then compose with `Bind` to propagate the first failure (later steps don't run; the failure just flows through).[^shortcircuit] It's useful for **making expected failure explicit and composable**.

`Result<TSuccess, TError>` has the same *two-case* shape as `Maybe<T>`, except the non-success case carries a reason (`TError`). `Maybe` models optionality; `Result` models failure *with* an explicit reason.

Prefer to compose with `Bind` until you need to branch, translate, or produce an output (often at a boundary/edge), then `Match`. [^checked-exceptions]

If you need to accumulate many errors (e.g., form validation) or you have several first-class outcomes, `Result` may not be the best fit.[^accumulation]

If you're coming from FP, this is closest to an `Either`/`Result`-style type.[^either]

### TL;DR
What it looks like (implementations for `User` left out for brevity):

```csharp
public record Error(string Code, string Message);
// Assume `repo` is in scope.

// Creating results:
Result<User, Error> okUser = Result<User, Error>.Ok(new User(/* ... */));
Result<User, Error> failed = Result<User, Error>.Fail(new Error("NotFound", "User not found"));

// Assume:
// Result<int, Error> ParseId(string inputIdFromRequest)
// Result<User, Error> DeactivateDecision(User user)

// Returning a Result from a function:
Result<User, Error> FindUserOrFail(IUserRepo repo, int id)
{
    User? user = repo.Find(id);
    if (user is null)
    {
        return Result<User, Error>.Fail(new Error("NotFound", $"User {id} not found"));
    }

    return Result<User, Error>.Ok(user);
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
</details>

On success, `Bind` passes the inner value to the next step; on failure, it forwards the `Error`. Short-circuiting allows the failure to propagate: after the first `Fail`, later steps are bypassed and the error flows through to the end. `Bind` *encodes* the control flow so your business logic doesn't have to repeat it.

> **Note:** You may also see this described as "railway switching", "bypassing", "error propagation", or "fail-fast".

Yes, this example uses a repository (a very .NET thing) and mutates a `User`. That's deliberate: I don't want this post to imply you should replace `exceptions` everywhere with `Result`.

The core idea is simple: `Bind` chains successes and short-circuits on the first failure.

#### The problem: explicit vs. implicit

In C#, fallible work is often handled with `exceptions`, or with explicit branching (`TryX`/guard clauses/status checks) depending on whether failure is expected.

**Option A: Implicit Control Flow (Exceptions)**

Method signatures often don't advertise failure when using `exceptions`, unlike `TryX`/`bool`-return patterns.[^checked-exceptions]
`DeactivateUser` (below) returns `void`, so failures aren't visible in the signature. In this style, it might throw for parsing/loading/saving and even for business-rule failures.

The following shows a style where expected failures are represented as `exceptions` (sometimes called "exceptions as control flow"; some may avoid this style). It's intentionally heavy-handed.

Typical C# code is often closer to: parse with `TryParse`, call a repo/service that may throw, then catch once at the boundary.

```csharp
// The implicit "User" entity used in the examples below
public class User
{
    public int Id { get; set; }
    public bool IsActive { get; set; }
}
```

`User` is **mutable** here to keep focus on `Result`. Prefer immutability where practical in domain code; some ecosystems (e.g., ORMs) still push you toward mutation.[^immutability]

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
    catch (Exception ex) when (ex is FormatException or OverflowException)
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

**Main point: in the code above, you're responsible for `null` checks, initializing the user variable outside `try/catch`, and stopping (early return/throwing an `exception`). It's noisy and easy to get wrong.**

In larger apps, `exceptions` often surface far from where you want domain context, so you either catch at boundaries or add local `try/catch` when you truly need extra context.

**Option B: Explicit Validation (Guard Clauses)**
To avoid throwing for expected failures, you often use `TryX`-style APIs, guard clauses, and early returns. It's linear, but still noisy.

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
        // logging omitted for brevity
        return DeactivateUserResult.InfraError;
    }
    if (user is null) return DeactivateUserResult.NotFound;

    if (!user.IsActive) return DeactivateUserResult.AlreadyInactive;

    // assuming an ORM that requires mutation
    user.IsActive = false;
    try
    {
        _repo.Save(user);
    }
    catch (Exception)
    {
        // logging omitted for brevity
        return DeactivateUserResult.InfraError;
    }
    return DeactivateUserResult.Success;
}
```

An enum gives you a status, but not a success payload. If you need to return data on success, you end up adding an `out` parameter, returning a tuple, or introducing a wrapper type.
Conventions are easy to violate: nothing stops you from returning `(user: null, error: null)` or populating both.

> **Note:** You can fix the "invalid combinations" problem with an `OperationStatus` hierarchy (e.g., `OperationSuccess` / `OperationFailure`) or a private constructor plus `Success(...)`/`Failure(...)` factories. That helps, but you still need good composition to avoid "check the status after every step."

`Result` packages these conventions + combinators into a reusable shape (`Ok(...)`/`Fail(...)`, `Map`/`Bind`).

#### The solution: the `Result` monad

`Result` returns *expected* failure as data (as long as your steps return `Result` rather than throwing), instead of using an `exception` jump. Unexpected `exceptions` still escape.

Now each step either produces the next value or propagates the first `Fail(...)`. This is often described as **short-circuiting**.[^shortcircuit]

Non-LINQ syntax (plain method chaining):

```csharp
Result<User, Error> result =
    ParseId(inputId)
        .Bind(FindUser)
        .Bind(DeactivateDecision);
```

> In `C#`, `string?` is a nullable *reference* annotation; `int?` is `Nullable<int>`. In Rust, `?` is an early-return operator for `Result`/`Option` (and other types that implement the `Try` pattern).

LINQ query syntax (`Select`/`SelectMany`) is in the appendix.

##### Procedural code detour
<details><summary>Procedural code detour (collapsed)</summary>
> The detour provides procedural context for readers new to FP; it's optional.

If `ParseId` returns `Result.Fail(...)`, the pipeline short-circuits; if `ParseId` returns `Result.Ok(...)`, the pipeline continues.

The key is that the steps (`ParseId`, `FindUser`, `DeactivateDecision`) don’t know they’re in a pipeline. For example, `FindUser` simply accepts an `int` and returns either `Result.Ok(...)` or `Result.Fail(...)`.

Who decides? `Bind`.

After `ParseId` runs, the `Result` is in one of two states:

* Ok: contains a success value
* Fail: contains an error

Internally, the `Result` type stores a flag and either a value or an error. `Result.Ok(...)` and `Result.Fail(...)` are factories.

Implementation-wise, your `Result` type stores some internal flag/tag (often something like `isSuccess`) plus either the success value or the error. `Result.Ok(...)` and `Result.Fail(...)` are just factory methods that create an instance of the `Result` class with that internal flag/tag set appropriately.

Because *both* success and failure are represented by the same `Result` type, you can always call `Bind` next, on failure or success.

`Bind` then does one of two things:

* If the current `Result` is `Ok`, `Bind` calls the next step (e.g., `FindUser`, passed in as a function/delegate) and returns *that* step’s `Result`.
* If the current `Result` is `Fail`, `Bind` skips the next step and returns the existing failure unchanged. It ignores the passed in step.

Finally, chaining works because every step returns a `Result`. This keeps the shape consistent so you can keep calling `Bind`. If a step returned an unrelated type (or `void`), the chain would break.

The key point: `Result` handles sequencing; steps just return a `Result`, and `Bind` ensures the next step runs after an Ok.

#### How to get out of a Result with Match

Translating between layers often means turning a `Result` into a different output shape via `Match`. In practice you'll often also want `MapError` (or `BindError`) to translate error types between layers without ending the pipeline.

```csharp
Result<int, Error> infraResult = ParseId(inputIdFromRequest);

string response = infraResult.Match(
        ok: id => $"OK: {id}",
        err: e => $"Bad request: {e.Code} - {e.Message}");
```

At boundaries (HTTP/CLI/public APIs), you typically translate into a DTO/status/`ProblemDetails`/exit code.

**IMPORTANT!** C# doesn't force you to handle a returned `Result`. Use an analyzer.[^unused-result]

### A tiny `Result` implementation

> If you're curious, try implementing `Result` yourself first.

This teaching implementation isn't production-ready (use *LanguageExt* or *CSharpFunctionalExtensions*) and is intentionally minimalist and unsafe around `default`/null. It stores `default` in the unused slot (don't read it), doesn't prevent `Ok(null)` / `Fail(null)`, doesn't guard against "returning null" from `Bind`, has no `async` support, no `Equals`/`GetHashCode`, and doesn't catch `exceptions` -- to keep the focus on the core shape.

Here's the implementation for `Result`:

```csharp
public sealed class Result<TSuccess, TError>
{
    private readonly TSuccess _value;
    private readonly TError _error;
    private readonly bool _isSuccess;

    private Result(TSuccess value, TError error, bool isSuccess)
    {
        _isSuccess = isSuccess;
        _value = value;
        _error = error;
    }

    // Unit
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
        if (_isSuccess)
        {
            return Result<U, TError>.Ok(f(_value));
        }

        return Result<U, TError>.Fail(_error);
    }

    public Result<U, TError> Bind<U>(Func<TSuccess, Result<U, TError>> f)
    {
        if (_isSuccess)
        {
            return f(_value);
        }

        return Result<U, TError>.Fail(_error);
    }

    public TResult Match<TResult>(Func<TSuccess, TResult> ok, Func<TError, TResult> err)
    {
        if (_isSuccess)
        {
            return ok(_value);
        }

        return err(_error);
    }
}
```

> Where is `Result.Unit(...)`? In monad terms: for `Result<_, TError>`, `Ok(...)` is **return/pure** (the monadic "unit"). `Fail(...)` is the constructor for the error case. Practically, `Result.Unit(...)` = `Result.Ok(...)`.

### Where `Result` fits (and where it doesn't)

Rule of thumb: `T?` for something that could be null, `Maybe<T>` for expected absence (no reason), `Result<TSuccess, TError>` for expected failures you'll handle, and `exceptions` often for bugs or unrecoverable failures.[^always-valid]
Also: model only the failure detail callers can act on; if `TError` is part of a public API, keep it small and stable.

**Prefer `Result` when:**

* **Failure is expected and recoverable:** validation/business rules, not found, auth failures, parsing user input.
* **You want refactor pressure (and sometimes exhaustiveness):** refactors become visible because failure is in the return type.
* **Failure is routine / on hot paths:** avoid throwing for control flow; prefer `TryParse`/`Result`-style returns.

**Prefer `exceptions` (or other types) when:**

* **It's a bug / broken invariant:** violated preconditions, "impossible states" → `exceptions` (e.g., `ArgumentNullException`).
* **Continuing is pointless / you need stack traces:** misconfiguration, out-of-memory, "dead end" aborts → `exceptions` / short-circuit.
* **You need accumulation:** `Bind` is short-circuiting; use `Validation<T>`/applicatives (or a combine API) for independent validations.


### Putting it together

Eventually you turn a `Result` into something your caller understands (HTTP response, CLI exit code, UI state, etc.). A boundary (the "edge" of the system) is a good place to `Match`.

> **Boundary/Application Layer:** the boundary (or edge) is where your program interacts with something you don't fully control (inputs, networks, storage, other systems).

See `HandleDeactivateRequest` below for a concrete example.

#### Example: deactivate a user
We want to deactivate a user given a user's `id` from an HTTP request (received as a **string**, parsed to an `int`).[^id]

This HTTP API/user service example is just a convenient boundary; the same idea applies to CLIs, jobs, message handlers, UI workflows, etc.

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
        // Workflow composition; the write happens at the boundary (see `HandleDeactivateRequest`).
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
                // If this throws, assume middleware/global handlers translate + log infra failures.
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

This computes `Result<User, Error>` internally, then `Match`es at the boundary (`HandleDeactivateRequest`) to produce the caller-facing output. In a real HTTP endpoint, you'd return `IActionResult`/`IResult` (not a `string`) and map `Error` to `ProblemDetails`/status codes.

#### Why is `_repo.Save(user)` inside `Match`?

`Save` is `I/O`. It can fail with domain-relevant outcomes (e.g., uniqueness conflicts) and unexpected infrastructure `exceptions` (timeouts, outages). If you want conflicts to be "expected failures," catch and translate the specific `exception` into a `Result` error; otherwise let truly unexpected `exceptions` bubble to boundary handlers.

### Why serializing `Result` directly can be awkward

In **public contracts**, serializing `Result` tends to leak an internal control-flow wrapper into your schema. Prefer `Match` into a DTO / HTTP status / `ProblemDetails` (unless using a custom converter).

Some `Result` types could expose public `Value`/`Error`/flags, which can make serialization even worse. If you serialize a `Result`-shaped class directly, you can end up with confusing "wrapper JSON" like this:

```json
{
  "isSuccess": false,
  "value": null,
  "error": { "code": "DbError", "details": { /* ... */ } }
}
```

Now your public API couples clients to an internal control-flow wrapper and can leak internal shapes. Clients have to interpret `isSuccess` + `value/error` *and* your HTTP status code. What if `isSuccess` is true and `error` contains an error? It's a weird situation.

### Async: the `Task<Result<...>>` nesting weirdness

Async note: once you mix `Task` and `Result`, you'll want async-aware combinators (`MapAsync`/`BindAsync`) to compose `Task<Result<...>>` without glue code. Rather than reimplement those helpers here, use a library that provides them.

### Recap

- `Result<TSuccess, TError>` makes expected failure explicit and composable.
- Use `Bind` for short-circuiting pipelines; `Match` to produce caller-facing output.
- For public contracts, unwrap `Result` into DTOs (rather than serializing it). Decide where you catch/translate `exceptions`.

### Appendix: LINQ query syntax (`Select`/`SelectMany`)
If you want `from`/`from`/`select` query syntax to compile, add these extension methods (or add them directly to `Result`). Other keywords like `where` require additional methods.

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

[^checked-exceptions]: Java has *checked exceptions* (`throws` forces callers to catch/declare them), but unchecked exceptions still exist. C# has no checked exceptions, so "might throw" usually isn't in the signature (unless documented).

[^immutability]: Mutation could make pipelines harder to reason about and test. Prefer immutability (`record` + `init`, or return a new value); I mutate here to keep focus on `Result` mechanics.

[^always-valid]: Vladimir Khorikov, [Always valid vs not always valid domain model](https://enterprisecraftsmanship.com/posts/always-valid-vs-not-always-valid-domain-model/).

[^unused-result]: C# lets you ignore return values, so a `Result` can be silently dropped. Use a Roslyn analyzer to flag unused `Result`s.

[^shortcircuit]: "Short-circuit" here: after the first failure, later steps aren't called; the failure value just propagates.

[^accumulation]: `Bind` is sequential and short-circuiting. If you need to accumulate independent validation errors, prefer a `Validation<T>`/applicative (or a dedicated `Combine` API). If you have several first-class outcomes, a union/tagged type is often a better model than forcing "success vs error".

[^either]: Closest analogue in FP is usually `Either` (often Left=error, Right=success, but conventions vary).

[^result-monad-precise]: More precisely: for a fixed error type, `Result<_, TError>` (like right-biased `Either`) forms a monad. See [Cats: Either](https://www.scala-exercises.org/cats/either). Practically, you have to commit to the same `TError` type throughout the entire pipeline, as that is how `Bind` is defined.
