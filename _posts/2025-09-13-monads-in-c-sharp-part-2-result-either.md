---
title: "Monads in C# (Part 2): Result (Either)"
date: 2025-09-13
description: "Build a small Result type in C# and use `Map`/`Bind`/`Match` to compose short-circuiting workflows with explicit errors."
---

**Previously in the series**: [List is a monad (part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/)

> _Note_: rewritten 2025-12-21.

In **Part 1** (`List`), we contrasted `Map` (`Select`) vs `Bind` (`SelectMany`) on `List<T>`, then built `Maybe<T>`.

If you read Part 1, you already know the shape: `Bind`/`SelectMany` chains steps, and the `Maybe` monad decides whether the next step runs.

The `Result` pattern (more precisely: `Result<_, TError>` as a monad) lets you sequence and compose computations that are expected to or could fail. You return `Ok(value)` or `Fail(error)`, then compose with `Bind` to propagate the first failure (later steps don’t run; the failure just flows through).[^shortcircuit]

`Result<TSuccess, TError>` has the same *two-case* shape as `Maybe<T>`, except the non-success case carries a reason (`TError`) instead of being empty. `Maybe` models optionality (not error handling); `Result` models failure *with* an explicit reason.

Prefer to keep values within `Result` and compose with `Bind` until you need to branch, translate, or produce an output (often at a boundary/edge), then `Match`. [^checked-exceptions]

If you need to accumulate many errors (e.g., form validation) or you have several first-class outcomes, `Result` may not be the best fit.[^accumulation]

If you're coming from FP, this is closest to an `Either`/`Result`-style type.[^either]

### TL;DR
What it looks like (implementations for user left out for brevity):

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

On success, `Bind` passes the inner value to the next step; on failure, it forwards the `Error`. Short-circuiting is literal for the remaining delegates you pass to `Bind`: after the first `Fail`, later steps aren’t invoked (but any side effects that already happened stay happened).

Yes, this example uses a repository and mutates a `User` which is a bit weird to do in FP. I could have used a squeaky clean, low-fat, low-carb, free-range, pure, side-effect free calculator example, but, it's a bit far removed from everyday code. That’s deliberate: it’s “real enough” to be motivating without implying you should replace `exceptions` everywhere with `Result`, or that you have to convert your entire codebase to a functional programming-esque one.

#### The problem: explicit vs. implicit

In C#, fallible work is often handled with exceptions, or with explicit branching (`TryX`/guard clauses/status checks) depending on whether failure is expected.

**Option A: Implicit Control Flow (Exceptions)**

Method signatures often don’t advertise failure when using `exceptions`, unlike `TryX`/`bool`-return patterns.[^checked-exceptions]
`DeactivateUser` (below) returns `void`, so failures aren’t visible in the signature. In this style, it might throw for parsing/loading/saving and even for business-rule failures.

The following shows a style where expected failures are represented as `exceptions` (“exceptions as control flow”, which is *often considered* an anti-pattern). It’s intentionally heavy-handed: it catches `Exception` and wraps at each step to highlight worst-case ergonomics.

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

In larger apps, exceptions often surface far from where you want domain context, so you either catch at boundaries (log/translate once) or add local `try/catch` only when you truly need extra context.

**Main point: in the code above, you’re responsible for `null` checks, catching, initializing the user variable outside try/catch, and stopping the pipeline on failure. It’s easy to repeat, it's noisy, and easy to get wrong.**

**Option B: Explicit Validation (Guard Clauses)**
To avoid throwing for expected failures, you often use `TryX`-style APIs, guard clauses, and early returns. It’s linear, but still noisy.

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

`User` is **mutable** here to keep focus on `Result`. Prefer immutability where practical in domain code; some ecosystems (e.g., ORMs) still push you toward mutation.[^immutability]

An enum gives you a status, but not a success payload. If you need to return data on success, you end up adding an `out` parameter, returning a tuple, or introducing a wrapper type.
Conventions are easy to violate: nothing stops you from returning `(user: null, error: null)` or populating both.

> **Note:** You can fix the “invalid combinations” problem with an `OperationStatus` hierarchy (e.g., `OperationSuccess` / `OperationFailure`) or a private constructor plus `Success(...)`/`Failure(...)` factories. That helps, but you still need good composition to avoid “check the status after every step.”

`Result` packages these conventions + combinators into a reusable shape (`Ok(...)`/`Fail(...)`, `Map`/`Bind`).


#### The solution: the Result monad

`Result` returns *expected* failure as data (as long as your steps return `Result` rather than throwing), instead of using an `exception` jump. Unexpected `exceptions` still escape.

Now each step either produces the next value or propagates the first `Fail(...)`. This is often described as **short-circuiting** or **fail-fast**.[^shortcircuit]

Non-LINQ syntax (plain method chaining):

```csharp
Result<User, Error> result =
    ParseId(inputId)
        .Bind(FindUser)
        .Bind(DeactivateDecision);
```

LINQ query syntax (`Select`/`SelectMany`) is in the appendix.

Translating between layers often means turning a `Result` into a different output shape via `Match`. For example, at a boundary you might translate into a response shape:

```csharp
Result<int, Error> infraResult = ParseId(inputIdFromRequest);

string response =
    infraResult.Match(
        ok: id => $"OK: {id}",
        err: e => $"Bad request: {e.Code} - {e.Message}");
```

`Match` returns any `TResult`. At boundaries (HTTP/CLI/public APIs), you typically translate into a DTO/status/`ProblemDetails`/exit code.
When translating, try not to erase diagnostics: log the original exception/cause (or carry it inside `TError`) instead of flattening everything into a string.

**IMPORTANT!** In C#, it’s still easy to ignore return values such as `Result`, which means that errors could go unnoticed. For a workaround, use an analyzer.[^unused-result]

### A tiny `Result` implementation

Aside: try implementing `Result` yourself first.
This teaching implementation (don’t ship it; use *LanguageExt* or *CSharpFunctionalExtensions*) is intentionally minimalist and unsafe around `default`/null: it stores `default` in the unused slot (don’t read it), it doesn’t prevent `Ok(null)` / `Fail(null)`, it doesn't prevent creating a null `Result`, doesn't have async support, and it doesn’t catch `exceptions`. These extra checks are intentionally omitted because I don't want to distract from the core structure of `Result`, and would likely end up massive otherwise.

In monad terms: for `Result<_, TError>`, `Ok(...)` is **return/pure** (the monadic “unit”). `Fail(...)` is the constructor for the error case (analogous to `Left(...)` for `Either`).

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
            return Result<U, TError>.Ok(f(_value!));
        }

        return Result<U, TError>.Fail(_error!);
    }

    public Result<U, TError> Bind<U>(Func<TSuccess, Result<U, TError>> f)
    {
        if (_isSuccess)
        {
            return f(_value!);
        }

        return Result<U, TError>.Fail(_error!);
    }

    public TResult Match<TResult>(Func<TSuccess, TResult> ok, Func<TError, TResult> err)
    {
        if (_isSuccess)
        {
            return ok(_value!);
        }

        return err(_error!);
    }
}
```

Note: in `C#`, `string?` is a nullable *reference* annotation; `int?` is `Nullable<int>`. In Rust, `?` is an early-return operator for `Result`/`Option` (and other types that implement the `Try` pattern).

### Unwrap at the boundary
At some point you turn a `Result` into something your caller understands (HTTP response, CLI exit code, UI state, etc.) or you need to do something with the error such as error handling. A boundary (the “edge” of the system) is a good place to `Match`.

> **Boundary / application layer:** parse/validate inputs, call repos/services, run workflow/domain decisions, then `Match` into a public output (`DTO`s/status/`ProblemDetails`/etc.).
See `HandleDeactivateRequest` below for a concrete example.

#### Why you shouldn’t naively serialize `Result`
Avoid serializing `Result` in **public contracts**: it leaks an internal control-flow wrapper into your schema. Prefer `Match` into a DTO / HTTP status / `ProblemDetails` (unless using a custom converter).
Some `Result` types could expose public `Value`/`Error`/flags, which can make serialization even worse.

If you serialize a `Result`-shaped class directly, you can end up with confusing “wrapper JSON” like this:

```json
{
  "isSuccess": false,
  "value": null,
  "error": { "code": "DbError", "details": { /* ... */ } }
}
```

Now your public API couples clients to an internal control-flow wrapper and can leak internal shapes. Clients have to interpret `isSuccess` + `value/error` *and* your HTTP status code, which invites contradictory states.


### Where `Result` fits (and where it doesn’t)

Rule of thumb: `T?`/`Maybe<T>` for expected absence (no reason), `Result<TSuccess, TError>` for expected failures you’ll handle, and exceptions for bugs or unrecoverable failures.[^always-valid]
Also: model only the failure detail callers can act on; if `TError` is part of a public API, keep it small and stable.

**Prefer `Result` when:**

* **Failure is expected and recoverable:** validation/business rules, not-found, auth failures, parsing user input.
* **You want refactor pressure (and sometimes exhaustiveness):** refactors become visible because failure is in the return type.
* **Failure is routine / on hot paths:** don’t throw for control flow; prefer `TryParse`/`Result`-style returns.

**Prefer exceptions (or other types) when:**

* **It’s a bug / broken invariant:** violated preconditions, “impossible states” → exceptions (e.g., `ArgumentNullException`).
* **Continuing is pointless / you need stack traces:** misconfiguration, out-of-memory, “dead end” aborts → exceptions / fail fast.
* **You need accumulation:** `Bind` is fail-fast; use `Validation<T>`/applicatives (or a combine API) for independent validations.


### Putting it together
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

Compute `Result<User, Error>` internally, then `Match` at the boundary (`HandleDeactivateRequest`) to produce the caller-facing output.
In a real HTTP endpoint, you’d typically return `IActionResult`/`IResult` (not a `string`) and map `Error` to `ProblemDetails`/status codes.

### Why is `_repo.Save(user)` inside `Match`?

`Save` is `I/O`. It can fail with domain-relevant outcomes (e.g., uniqueness conflicts) and unexpected infrastructure exceptions (timeouts, outages). If you want conflicts to be “expected failures,” catch and translate the specific exception into a `Result` error; otherwise let truly unexpected exceptions bubble to boundary handlers.

### Async: the `Task<Result<...>>` nesting weirdness

Async note: once you mix `Task` and `Result`, you’ll quickly want async-aware combinators (`MapAsync`/`BindAsync`) so you can compose `Task<Result<...>>` without glue code. Rather than reimplement those helpers here in a likely buggy fashion, use a library that provides them.

### Recap

- `Result<TSuccess, TError>` makes expected failure explicit and composable.
- Use `Bind` for fail-fast pipelines; `Match` to produce a caller-facing output (DTO/status/`ProblemDetails`, CLI output, etc.).
- Avoid serializing `Result` as a public contract; unwrap into DTOs. Exceptions still exist - decide where you catch/translate them.
- Once you mix `Task` and `Result`, you’ll want async-aware helpers (`MapAsync`/`BindAsync`) from a library.

### Appendix: LINQ query syntax (`Select`/`SelectMany`)
If you want the simple `from`/`from`/`select` query syntax to compile, add these extension methods (or add the same methods directly to `Result`). Other query keywords like `where` require additional methods.

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
[^immutability]: Mutation could make pipelines harder to reason about and test. Prefer immutability (`record` + `init`, or return a new value); I mutate here to keep focus on `Result` mechanics.
[^always-valid]: Vladimir Khorikov, [Always valid vs not always valid domain model](https://enterprisecraftsmanship.com/posts/always-valid-vs-not-always-valid-domain-model/).
[^unused-result]: C# lets you ignore return values, so a `Result` can be silently dropped. Use a Roslyn analyzer to flag unused `Result`s.
[^shortcircuit]: “Short-circuit” here: after the first failure, later steps aren’t called; the failure value just propagates.
[^accumulation]: `Bind` is sequential and fail-fast. If you need to accumulate independent validation errors, prefer a `Validation<T>`/applicative (or a dedicated `Combine` API). If you have several first-class outcomes, a union/tagged type is often a better model than forcing “success vs error”.
[^either]: Closest analogue in FP is usually `Either` (often Left=error, Right=success, but conventions vary).
