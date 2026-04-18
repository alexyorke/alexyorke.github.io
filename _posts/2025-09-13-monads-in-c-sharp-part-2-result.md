---
title: "Monads in C# (Part 2): Result"
date: 2025-09-13
description: "Build a small Result type in C# and use `Map`/`Bind`/`Match` to compose short-circuiting workflows with explicit errors."
---

**Previously in the series**: [List is a monad (part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/)

_Last updated 2026-04-18._

In **Part 1** (`List`), we contrasted `Map` (`Select`) vs `Bind` (`SelectMany`) on `List<T>`, then built `Maybe<T>`.

If you read Part 1, you already know the pattern: `Bind`/`SelectMany` chains steps, and `Maybe` decides whether the next step runs.

The `Result` monad[^result-monad-precise] lets you compose operations that can fail. You return `Ok(value)` or `Fail(error)`, then compose with `Bind` to propagate the first failure. After the first `Fail`, later steps do not run, and the same error value is returned to the end of the pipeline. It's useful for **making expected failure explicit and composable**.

### TL;DR
What it looks like (implementations for `User` left out for brevity):

> **Terminology:** In this post, I use `application boundary` for the part of the system that converts internal results into caller-facing output. In other writing, you may also see this called the `edge`, the `edge of the app`, or the `system boundary`.

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

// Handle at the application boundary (or when converting between layers):
string message = result.Match(
    ok:  _ => "User deactivated",
    err: e => $"Deactivate failed: {e.Code} - {e.Message}");
```

On success, `Bind` passes the inner value to the next step; on failure, it forwards the `Error`. Short-circuiting allows the failure to propagate: after the first `Fail`, later steps are bypassed and the same error value is returned to the end of the pipeline. `Bind` encodes the control flow so your business logic doesn't have to repeat it.

> **Note:** You may also see this described as "railway switching", "bypassing", "error propagation", or "fail-fast".

In F#, this style is more natural. In C#, I use it selectively: mainly when several operations can fail and I want expected failure visible in the return type. For one-off parse/check code, `Try*` APIs or exceptions handled at the application boundary are often clearer.

### The problem: explicit vs. implicit

In C#, operations that can fail are often handled with `exceptions`, or with explicit branching (`TryX`/guard clauses/status checks) depending on whether failure is expected.[^expected-vs-exceptional]

**Option A: Implicit Control Flow (Exceptions)**

Method signatures often don't advertise failure when using `exceptions`, unlike `TryX`/`bool`-return patterns.[^checked-exceptions]
`DeactivateUser` (below) returns `void`, so failures aren't visible in the signature. In this style, it might throw for parsing/loading/saving and even for business-rule failures.



```csharp
private readonly IUserRepo _repo;

public void DeactivateUser(string inputId)
{
    if (inputId is null) throw new ArgumentNullException(nameof(inputId));

    if (!int.TryParse(inputId, out var id))
        throw new InvalidUserIdException(inputId);

    User user = _repo.Find(id) ?? throw new UserNotFoundException(id);

    if (!user.IsActive)
        throw new UserAlreadyInactiveException(id);

    user.IsActive = false;

    // If this throws, it propagates to middleware or another handler at the application boundary, which can log and convert it.
    _repo.Save(user);
}
```


**Failure is implicit in the return type; when you need local recovery or conversion, you typically rely on `try/catch` or repeated status checks.**

**Option B: Explicit Validation (`TryX`/Guard Clauses)**
To avoid throwing for expected failures, use guard clauses and early returns.
I don't call this `TryDeactivateUser`, because the standard .NET `Try*` pattern conventionally returns `bool` and uses an `out` parameter. Here I want a richer status enum.

```csharp
private readonly IUserRepo _repo;

public enum DeactivateUserResult
{
    Success,
    InvalidId,
    NotFound,
    AlreadyInactive
}

public DeactivateUserResult DeactivateUser(string inputId)
{
    if (!int.TryParse(inputId, out var id)) return DeactivateUserResult.InvalidId;

    var user = _repo.Find(id); // unexpected infrastructure exceptions propagate
    if (user is null) return DeactivateUserResult.NotFound;

    if (!user.IsActive) return DeactivateUserResult.AlreadyInactive;

    user.IsActive = false;
    _repo.Save(user); // unexpected infrastructure exceptions propagate
    return DeactivateUserResult.Success;
}
```

If you genuinely want local conversion here, catch a specific repository exception you intend to turn into a local status rather than catching `Exception`.

An enum gives you a status, but not a success payload. If you need to return data on success, you end up adding an `out` parameter, returning a tuple, or introducing a wrapper type.
Conventions are easy to violate: nothing stops you from returning `(user: null, error: null)` or populating both.

`Result` packages these conventions and combinators into a reusable type and API (`Ok(...)`/`Fail(...)`, `Map`/`Bind`).

### The solution: the `Result` monad

`Result` returns *expected* failure as data (as long as your steps return `Result` rather than throwing), instead of relying on a thrown `exception` for control flow. Unexpected `exceptions` still propagate.

Now each step either produces the next value or propagates the first `Fail(...)`.

Non-LINQ syntax (plain method chaining):

```csharp
Result<User, Error> result =
    ParseId(inputId)
        .Bind(FindUser)
        .Bind(DeactivateDecision);
```

That `Bind` chain is the simplest linear pipeline case: each step only needs the previous value. It's useful, but it's **not** the general case.[^acid-test]

When you need to reuse earlier values, LINQ query syntax avoids nested lambdas (directly inspired by Haskell’s `do`-notation):

```csharp
Result<User, Error> result =
    from id    in ParseId(inputId)
    from user  in FindUser(id)
    from posts in FindPostsByUserId(id)
    from done  in DeactivateDecisionWithPosts(user, posts)
    select done;
```


If you want LINQ query syntax (`from`/`select`) to compile for this `Result`, see the appendix.

Converting between layers often means turning a `Result` into a different output type via `Match`. In practice you'll often also want `MapError` (or `BindError`) to convert error types between layers without ending the pipeline.

```csharp
Result<int, Error> infraResult = ParseId(inputIdFromRequest);

string response = infraResult.Match(
        ok: id => $"OK: {id}",
        err: e => $"Bad request: {e.Code} - {e.Message}");
```

At the application boundary (HTTP/CLI/public APIs), you typically convert the result into a DTO/status/`ProblemDetails`/exit code.

**IMPORTANT!** C# doesn't force you to handle a returned `Result`. Use an analyzer.[^unused-result]

### A tiny `Result` implementation

> If you're curious, try implementing `Result` yourself first.

This teaching implementation is intentionally minimal and not production-ready. Use a library (below) for real code.

If you want an ecosystem rather than a teaching implementation, look at:

- [LanguageExt](https://github.com/louthy/language-ext): full FP ecosystem for C# (LINQ support, `Fin<A>`, higher-kinded traits; see [Paul Louth's series](https://paullouth.com/higher-kinds-in-c-with-language-ext/)).
- [CSharpFunctionalExtensions](https://github.com/vkhorikov/CSharpFunctionalExtensions): smaller, pragmatic `Result`/`Maybe` types.
- [Danom](https://github.com/pimbrouwers/Danom): another small Result/Option-style OSS library.
- [ErrorOr](https://github.com/amantinband/error-or): an `ErrorOr<T>` style that reduces type-parameter noise.

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

### Where `Result` is useful (and where it isn't)

Rule of thumb: `T?` for something that could be null, `Maybe<T>` for expected absence (no reason), `Result<TSuccess, TError>` for expected failures you'll handle, and `exceptions` often for bugs or unrecoverable failures.[^always-valid]

`Result` is most useful when a cohesive slice of code already returns it consistently; used in isolation, it often adds more ceremony than value.

**Prefer `Result` when:**

* **Failure is expected and recoverable:** validation/business rules, not found, auth failures, parsing user input.
* **You have a multi-step workflow:** the composition benefit matters once several steps that can fail need to fit together cleanly.

**Prefer `exceptions` (or other types) when:**

* **It's a bug / broken invariant:** violated preconditions, "impossible states" → often `exceptions` (e.g., `ArgumentNullException`).
* **You need accumulation:** `Bind` is short-circuiting; use `Validation<T>`/applicatives (or a combine API) for independent validations.[^accumulation]

### A note on ergonomics (and why this can feel less idiomatic in C#)
`Result` is idiomatic in F#; in C# it can feel more verbose.

- In F#, discriminated unions and computation expressions make `Result` workflows terse.
- In C#, you pay more ceremony (generic type arguments, `Ok(...)` factories, async nesting, etc.). If you push this everywhere, new-reader overhead is real.
- Even if C# gets discriminated unions, that improves representation and pattern matching but does **not** give you F#-style computation expressions or type inference.

Practical tips if you *do* use `Result` in C#:

- Keep it local (often: application boundaries and workflows), not everywhere.
- Prefer LINQ query syntax (`from`/`select`) once you need to reuse earlier values or branch (more on that below).
- Consider a single error type / `ErrorOr<T>`-style API if the two-parameter shape gets too noisy.

For example:

```csharp
// at the top of the file:
using UserResult = Result<User, Error>;

UserResult r1 = FindUserOrFail(repo, 123);

var r2 =
    ParseId(inputIdFromRequest)
        .Bind(id => FindUserOrFail(repo, id));
```

Many libraries provide implicit conversions (`Ok<T>`/`Err<E>` wrappers or `using static` helpers) so you don't write `Result<TSuccess, TError>.Ok(...)` everywhere.

### Putting it together

Eventually you turn a `Result` into something your caller understands (HTTP response, CLI exit code, UI state, etc.). The application boundary is a good place to `Match`.

#### Example: deactivate a user
We want to deactivate a user given a user's `id` from an HTTP request (received as a **string**, parsed to an `int`).[^id]

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
        // Workflow composition; the write happens at the application boundary (see `HandleDeactivateRequest`).
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
                // If this throws, assume a handler at the application boundary logs it and converts it for the caller.
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

This computes `Result<User, Error>` internally, then `Match`es at the application boundary (`HandleDeactivateRequest`) to produce caller-facing output. In a real HTTP endpoint, you'd return `IActionResult`/`IResult` (not a `string`) and map `Error` to `ProblemDetails`/status codes.

#### Why is `_repo.Save(user)` inside `Match`?

`Save` is I/O and can fail. Catch and convert domain-relevant exceptions (e.g., uniqueness conflicts) into a `Result` error; let unexpected infrastructure `exceptions` propagate to handlers at the application boundary.

### Why serializing `Result` directly adds wrapper fields

On a **public API surface**, serializing `Result` tends to leak an internal control-flow wrapper into your schema. Prefer `Match` into a DTO / HTTP status / `ProblemDetails` (unless using a custom converter).
Serializing a `Result` class directly produces wrapper JSON like this:

```json
{
  "isSuccess": false,
  "value": null,
  "error": { "code": "DbError", "details": { /* ... */ } }
}
```

### Note on async: `Task<Result<...>>` nesting requires async-aware combinators

Mixing `Task` and `Result` gives `Task<Result<...>>`, which plain LINQ doesn't compose. Use async-aware combinators (`BindAsync`/`MapAsync`) or a library that provides them.

### Recap

- `Result<TSuccess, TError>` makes expected failure explicit and composable.
- It's a targeted tool, not a blanket replacement for `Try*` APIs or `exceptions`.
- Use `Bind` for short-circuiting pipelines; `Match` to produce caller-facing output.
- For public API surfaces, unwrap `Result` into DTOs (rather than serializing it). Decide where you catch/convert `exceptions`.

Part 3 coming soon.

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

### Further reading

- [Ergonomically fitting monads into imperative languages](https://odr.chalmers.se/items/91bf8c4b-93dd-43ca-8ac2-8b0d2c62a581) — master's thesis on `do`-notation-style syntax for monads in imperative languages ([C# prototype](https://github.com/master-of-monads/monads-cs/blob/89netram/mcs/Mcs/SamplePrograms/MonadSamples.cs)).
- [Paul Louth's higher-kinds in C# series](https://paullouth.com/higher-kinds-in-c-with-language-ext/) — higher-kinded abstractions and monads in C# with LanguageExt.
- [jerf's monad tutorial acid test](https://jerf.org/iri/post/2928/) — litmus test for whether a monad implementation supports more than linear pipelines.
- [Scott Wlaschin's Railway Oriented Programming](https://fsharpforfunandprofit.com/rop/) — the canonical F# introduction to `Result`-style composition.

[^id]: In real systems, prefer a strongly typed ID (e.g., `UserId`) over primitives. Here I keep it simple: `string` at the application boundary, parse to `int`, focus on `Result`.

[^checked-exceptions]: Java has *checked exceptions* (`throws` forces callers to catch/declare them), but unchecked exceptions still exist. C# has no checked exceptions, so "might throw" usually isn't in the signature (unless documented).

[^always-valid]: Vladimir Khorikov, [Always valid vs not always valid domain model](https://enterprisecraftsmanship.com/posts/always-valid-vs-not-always-valid-domain-model/).

[^unused-result]: C# lets you ignore return values, so a `Result` can be silently dropped. Use a Roslyn analyzer to flag unused `Result`s.

[^accumulation]: `Bind` is sequential and short-circuiting. If you need to accumulate independent validation errors, prefer a `Validation<T>`/applicative (or a dedicated `Combine` API). If you have several first-class outcomes, a union/tagged type is often a better model than forcing "success vs error".

[^acid-test]: A useful criterion for monadic composition is whether you can branch on an intermediate value and reuse earlier bound values later in the workflow. LINQ query syntax supports that naturally; plain `.Bind().Bind()` chaining quickly degenerates into nested lambdas.

[^result-monad-precise]: Strictly, `Result` is a data type; it becomes a monad when paired with `Ok`/`Map`/`Bind` satisfying the monad laws (left identity, right identity, associativity). See [Cats: Either](https://www.scala-exercises.org/cats/either).

[^expected-vs-exceptional]: See the [.NET design guidelines on exceptions and performance](https://learn.microsoft.com/dotnet/standard/design-guidelines/exceptions-and-performance): prefer return values and `Try*` for expected failures; use `exceptions` for exceptional program states.
