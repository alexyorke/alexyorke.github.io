---
title: "Monads in C# (Part 2): Result (Either)"
date: 2025-09-13
description: "Build a small Result type in C# and use `Map`/`Bind`/`Match` to compose short-circuiting workflows with explicit errors."
---

**Previously in the series**: [List is a monad (part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/)

> _Note_: This post was substantially rewritten on 2025-12-21.

In **Part 1**, we used `List<T>` to contrast `Map` (LINQ `Select`) vs `Bind` (LINQ `SelectMany`/`FlatMap`), and built `Maybe<T>` to chain optional steps.

The `Result` monad sequences computations that could fail. Each step either produces a successful value or short-circuits with an `Error`, until you handle it. Use it when you want failures (and their reasons) to be explicit in the type.

It’s structurally like `Maybe<T>`/`Option<T>` for composition (they're both monads), except `Maybe` models absence while `Result` models failure with an error value.

That turns error handling from implicit control flow into an explicit return value, making pipelines linear and removing the need for scattered `throw`s[^checked-exceptions] and defensive checks.

### Quick preview: the end goal
Before we get into the "why", here’s what using `Result` looks like in practice:

```csharp
// A simple custom error payload used in this post (this is **not** part of `Result` itself):
public record Error(string Code, string Message);

string inputId = inputIdFromRequest;
Result<User, Error> result =
    ParseId(inputId)
        .Bind(FindUser)
        .Bind(DeactivateDecision);

// Unwrap once at the boundary:
string message = result.Match(
    ok:  _ => "User deactivated",
    err: e => $"Deactivate failed: {e.Code} - {e.Message}");
```

This can look “magical” if you’re used to procedural code with `var id = ...; var user = ...;`, so here’s the type story:

- `ParseId : string -> Result<int, Error>`
- `FindUser : int -> Result<User, Error>`
- `DeactivateDecision : User -> Result<User, Error>`
- `Bind : Result<T, Error> -> (T -> Result<U, Error>) -> Result<U, Error>`

`Bind(FindUser)` is just C# method-group shorthand for `Bind(id => FindUser(id))` — the `int` inside the successful `Result` becomes the input to `FindUser`. If `ParseId` failed, `Bind` never calls `FindUser`; it just forwards the `Error`.

#### The problem: explicit vs. implicit

Typically, when you need to handle operations that can fail, you end up in one of two styles: rely on **Implicit Control Flow** (exceptions) or write **Verbose Validation** (guard clauses).

**Option A: Implicit Control Flow (Exceptions)**
Typically, the method signature doesn't tell you what can go wrong.[^checked-exceptions] `DeactivateUser` returns `void`, yet it can throw while parsing/loading, or later via `null`s and business rules.

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

In small snippets, throw sites are obvious. In larger apps, exceptions can come from anywhere, pushing you toward `try/catch` scaffolding.

**You’re responsible for `null` checks, catching, and stopping the pipeline on failure—easy to repeat and easy to get wrong.**

**Option B: Explicit Validation (Guard Clauses)**
If you want to keep exceptions for truly exceptional cases, you end up with guard clauses and early returns. The control flow stays linear and explicit, but the validation checks get interleaved with the work.

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
    if (!int.TryParse(inputId, out var id))
        return DeactivateUserResult.InvalidId;

    var user = _repo.Find(id);
    if (user is null)
        return DeactivateUserResult.NotFound;

    if (!user.IsActive)
        return DeactivateUserResult.AlreadyInactive;

    user.IsActive = false;
    _repo.Save(user);
    return DeactivateUserResult.Success;
}
```

> **Note:** In the examples in this post, `User` is treated as a **mutable** entity (`user.IsActive = false;`). In real domain code, prefer immutability where you can, but that’s out of scope for this post.[^immutability]

At this point you might reach for `tuples` (e.g., `(bool Success, User? User, string Error)`).

However, tuples lack invariants. You can accidentally create a tuple with `Success = true` AND `Error = "Failed"`. You can also ignore the `Success` boolean and read the `User` property directly, causing `NullReferenceException`s.

`Result` encapsulates the state, making invalid combinations unrepresentable.

#### The solution: short-circuiting, as data

Could you model this as an `OperationStatus` base type with `OperationSuccess` / `OperationFailure` subclasses? Sure—that makes invalid combinations unrepresentable. `Result` is still useful because it standardizes composition (`Map`/`Bind`) across the whole pipeline.

`Result` models operation outcomes as values. Unlike `exceptions` (which perform an "Unconstrained Jump" up the stack to an unknown handler), `Result` creates a linear flow. The error travels exactly one step at a time, strictly following the return path. It is deterministic control flow.

Think of `Result` as the "Composable" version of the standard C# `Try...` pattern.[^out-var]
`int.TryParse` returns `bool` and uses `out int result`. `Result<int, Error>` wraps those two pieces (the success flag and the value) into a single object, allowing you to chain steps without stopping to declare temporary variables.

Now you can rewrite Option B as a pipeline: each step either produces the next value or stops with an `Error`.

We’ll keep using the same `Error` payload from the quick preview.

If you prefer LINQ query syntax, the same pipeline can be written as:

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
Here’s a small teaching implementation. Don’t use it in production; if you’re shipping this, use a library instead (e.g., *LanguageExt*, *CSharpFunctionalExtensions*, or *FluentResults*).

This teaching version assumes you don’t call `Ok(null)` / `Fail(null)` for reference types.
It also uses `default` to fill the unused slot; in real code you may want a design that avoids relying on `default` (especially if you want value-type errors).

```csharp
public sealed class Result<TSuccess, TError>
{
    private readonly TSuccess? _value;
    private readonly TError? _error;

    public bool IsSuccess { get; }
    public bool IsFailure => !IsSuccess;

    private Result(TSuccess? value, TError? error, bool isSuccess)
    {
        IsSuccess = isSuccess;
        _value = value;
        _error = error;
    }

    // OK: Wrap a value into the container.
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

    // MAP: Transform the success value.
    public Result<U, TError> Map<U>(Func<TSuccess, U> f)
    {
        if (IsSuccess)
        {
            return Result<U, TError>.Ok(f(_value!));
        }

        return Result<U, TError>.Fail(_error!);
    }

    // BIND: Chain a Result-returning function (flatmap).
    public Result<U, TError> Bind<U>(Func<TSuccess, Result<U, TError>> f)
    {
        if (IsSuccess)
        {
            return f(_value!);
        }

        return Result<U, TError>.Fail(_error!);
    }

    // MATCH: Unwrap at the boundary.
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

#### `Map` vs `Bind`: a quick cheat sheet
Both `Map` and `Bind` run a function **only on success** and propagate failures unchanged.
The only difference is what your function returns:

- Use `Map` for `TSuccess -> U`
- Use `Bind` for `TSuccess -> Result<U, TError>`

If you accidentally `Map` a function that already returns a `Result`, you’ll get a nested container (`Result<Result<...>>`). `Bind` is the flattening map that avoids that:

Rule of thumb: **if the function you’re passing already returns a `Result`, reach for `Bind`**. Otherwise, use `Map`.

### Unwrap at the boundary
> **Boundary:** validate inputs, run domain logic, then `Match` into a public output (`DTO`s/status/`ProblemDetails`).
> Don’t ignore returned `Result` values—use analyzers to enforce this.[^unused-result]

```csharp
Result<int, string> result = Result<int, string>.Ok(42);

string output = result.Match(
    ok:  value => $"Success: {value}",
    err: error => $"Error: {error}"
);
```

#### Why you shouldn’t serialize `Result`
Don’t serialize `Result` directly. It leaks internal representation into your public contract. `Match` it into `DTO`s/status codes/`ProblemDetails` instead.

Many `Result` implementations expose `Value`/`Error` (and flags like `IsSuccess`) as public properties. A generic serializer will happily turn that internal shape into your public API—it just sees public properties and emits them (often with a camelCase naming policy), e.g.:

```json
{
  "isSuccess": true,
  "isFailure": false,
  "error": null,
  "value": { "id": 123, "isActive": false }
}
```

Yikes. That wrapper is awkward, and it’s also brittle: now your public contract includes `isSuccess`/`isFailure` and your internal error/value shape. Unwrap at the boundary with `Match`, and return something that’s meant to be public (`DTO`s, status codes, `ProblemDetails`, etc.).
Don’t serialize `Result`. It’s an internal wrapper; `Match` it into a `DTO`/status/`ProblemDetails` instead.

### Why bother?
What do you get for returning `Result` instead of throwing or using "magic values"?
*   **Explicit Signatures:** `Result<User, Error>` tells you up front that failure is on the table.
*   **Fewer ad-hoc conventions:** No `-1`, no `null`, no “special string means error.”
*   **Testability:** Tests can assert the outcome *and* the specific error (`Code`, type, message) without exception scaffolding.

### Where `Result` fits (and where it doesn’t)
Rule of thumb: use `T?` for “missing data”; use `Result<TSuccess, TError>` for “this operation can fail with a reason.”

`Result` works best for **domain logic**: failures you expect and want to handle. It doesn’t replace exceptions; it just keeps them in their lane.[^always-valid]

1.  **Infrastructure:** For technical failures (DB/network outages, timeouts, unexpected I/O errors), exceptions handled at the boundary (middleware/logging/global handlers) are often a good fit.
2.  **Bugs:** Violated preconditions are programmer errors—throw (`ArgumentNullException`, `ArgumentException`, etc.) rather than returning a domain `Result`.
3.  **Accumulation:** `Bind` stops at the first `Error`. If you need to collect *all* validation errors, use a validation type that accumulates errors instead of short-circuiting.

> **Note:** `Result` short-circuits on the first `Error`. For “collect all errors” validation, use a type that accumulates (e.g., `List<Error>`).

### Putting it together
#### Example: deactivate a user
We want to deactivate a user given an `id` from an HTTP request (received as a **string**, parsed to an `int`).[^id]

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

The idea: compute a `Result<User, Error>` in your internal workflow. Notice that the explicit `if` checks and guard clauses from the "Problem" examples have disappeared—they are now handled automatically inside `Bind`. We then unwrap the result once at the boundary in `HandleDeactivateRequest`.

A few pragmatic notes:

- **Where did the variables go?** `Bind(FindUser)` is the same as `Bind(id => FindUser(id))`. Method-group syntax hides the variable name, but the value still flows step-by-step.
- **Does this require immutability?** No. `Result` is about making failure explicit and composable. This example mutates `user.IsActive` to keep focus on the mechanics; in real domain code, prefer returning a new immutable value where you can.[^immutability]

#### Why is `_repo.Save(user)` inside `Match`?
`Save` is a side effect and often fails via exceptions (DB/network outages, timeouts). In this post we keep those **infrastructure failures** as exceptions handled at the boundary (middleware/global handlers), and we use `Result` for **expected domain failures** (invalid ID, not found, already inactive). See “Where `Result` fits” above.
### Async: the `Task<Result<...>>` nesting weirdness

In async code, your types often become `Task<Result<T, Error>>`. `await` unwraps the `Task`, not the `Result`, so without helpers you end up `await`ing and branching between steps.

If you want fluent pipelines, use a library (or write your own extensions) that provides `Map`/`Bind` for `Task<Result<...>>`, e.g.:

- **[CSharpFunctionalExtensions](https://github.com/vkhorikov/CSharpFunctionalExtensions)**
- **[LanguageExt](https://github.com/louthy/language-ext)**

```csharp
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

You now have three monads in your toolkit: `List` (multiple values), `Maybe` (optional values), and `Result` (possible failure). They all share the same interface (`Bind`/`SelectMany`), allowing you to solve complex flow problems with simple blocks.

**Next in the series**: [Monads in C# (Part 3): The Reader Monad](https://alexyorke.github.io/2025/12/20/monads-in-c-sharp-part-3-the-reader-monad/)

[^id]: In real systems, use a Strongly Typed ID (e.g., `UserId`) rather than a bare number to avoid "Primitive Obsession." This post uses `string` at the boundary and parses to `int` to keep the example focused on `Result` composition.
[^checked-exceptions]: Java has *checked exceptions*: methods can declare them with a `throws` clause and callers must catch/declare them. C# has no checked exceptions, so “what might throw” usually isn’t visible in the method signature unless it’s documented (e.g., XML `<exception>` docs).
[^immutability]: Mutating domain objects makes pipelines harder to reason about and test. Prefer immutable `record`s (and returning a new value) where you can; this post sticks to mutation to keep the focus on `Result` composition.
[^out-var]: C# supports inline `out` variable declarations (C# 7): e.g., `if (int.TryParse(input, out var id)) { ... }`. This makes a single `Try...` step fairly composable inside an `if`, but it doesn’t scale to multi-step pipelines the way `Result` + `Bind` does.
[^always-valid]: Vladimir Khorikov, [Always valid vs not always valid domain model](https://enterprisecraftsmanship.com/posts/always-valid-vs-not-always-valid-domain-model/).
[^unused-result]: C# allows ignoring return values, so a `Result` can be silently dropped. `exceptions` “force” handling by crashing; with `Result`, use a Roslyn analyzer to flag unused `Result`s (ideally as an error) so “oops” becomes a compile-time failure instead of a runtime crash.
