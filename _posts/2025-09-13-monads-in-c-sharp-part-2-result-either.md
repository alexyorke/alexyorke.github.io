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

#### The problem: explicit vs. implicit

Typically, when you need to handle operations that can fail, you end up in one of two styles: rely on **Implicit Control Flow** (exceptions) or write **Verbose Validation** (guard clauses).

**Option A: Implicit Control Flow (Exceptions)**
Typically, the method signature doesn't tell you what can go wrong, e.g., if an exception could be thrown.[^checked-exceptions] `DeactivateUser` returns `void`, yet it can throw parsing exceptions (`ArgumentNullException` / `FormatException` / `OverflowException`), and later failures may show up as runtime exceptions (e.g., `NullReferenceException` if `user` is null) or more specific exceptions (e.g., `InvalidOperationException` for a violated business rule).

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

In these small snippets, throw sites are obvious. In larger apps, exceptions can come from anywhere (parsing, mapping, `I/O`, `null`s), so composition pushes you toward `try/catch` scaffolding, either scattered around each step or wrapped around large blocks.

**The point is, you are responsible for writing these `null` checks, handling exceptions, declaring `User` outside of the `try/catch` so it can be used in subsequent steps, and ensuring that computation doesn't continue if a step failed.** This logic is repeated many, many, times throughout typical programs, and is easy to get wrong.

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

But hold on, couldn't I just make an abstract class called `OperationStatus`, creating two classes that inherit from it, `OperationSuccess` and `OperationFailure`? You can, and this would make the invalid combination unrepresentable. The point isn't _just_ making the invalid combination unrepresentable, it's about composition, too. It's the whole pipeline, it's the ability to compose multiple monads together that don't need to know about each other.

#### The solution: short-circuiting, as data

`Result` models operation outcomes as values. Unlike `exceptions` (which perform an "Unconstrained Jump" up the stack to an unknown handler), `Result` creates a linear flow. The error travels exactly one step at a time, strictly following the return path. It is deterministic control flow.

Think of `Result` as the "Composable" version of the standard C# `Try...` pattern.[^out-var]
`int.TryParse` returns `bool` and uses `out int result`. `Result<int, Error>` wraps those two pieces (the success flag and the value) into a single object, allowing you to chain steps without stopping to declare temporary variables.

Now you can rewrite Option B as a pipeline: each step either produces the next value or stops with an `Error`.

We'll use a simple custom error payload in the examples below (this is **not** part of `Result` itself):

```csharp
// The method signature remains `Result<User, Error>` regardless of new failure modes.
public record Error(string Code, string Message);
```

```csharp
string inputId = inputIdFromRequest;
Result<User, Error> result =
    ParseId(inputId)
        .Bind(FindUser)
        .Bind(DeactivateDecision);

// Note: we'll handle the side-effect (`Save`) at the boundary using `Match` below.
string message = result.Match(
    ok:  _ => "User deactivated",
    err: e => $"Deactivate failed: {e.Code} - {e.Message}");
```

> **Note:** `Result` is designed to **short-circuit** (stop at the first `Error`). If you need to **accumulate** multiple errors (e.g., validating a form where you want to show all missing fields at once), use a validation type that returns a `List<Error>` instead. Additionally, try not to shoe-horn `Result` into situations where it doesn't make sense. If there are other outcomes other than success/fail such as a neutral outcome, then `Result` may not be appropriate for that situation. For example, if you need to return a list of all failed and successful jobs, `Result` is only pass/fail, and might be non-idiomatic to use `Result` in this case.

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

    // "Return" (or "Pure"): Wraps a raw value into the container.
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

    // MAP: Transforms the data if successful. If the Result is a Failure, this is skipped entirely.
    // The Short-Circuit: If this Result is already a Failure, the function 'f' never runs,
    // and the existing error is passed along.
    public Result<U, TError> Map<U>(Func<TSuccess, U> f)
    {
        if (IsSuccess)
        {
            return Result<U, TError>.Ok(f(_value!));
        }

        return Result<U, TError>.Fail(_error!);
    }

    // BIND (LINQ SelectMany): Chains an operation that *might fail*.
    // Unlike Map (which just transforms data), Bind gives the function a chance to switch
    // the state from Success to Failure.
    // Structurally: It flattens nested Result<Result<...>> back into a single Result.
    public Result<U, TError> Bind<U>(Func<TSuccess, Result<U, TError>> f)
    {
        if (IsSuccess)
        {
            return f(_value!);
        }

        return Result<U, TError>.Fail(_error!);
    }

    // MATCH (Destructor): The "Exit Door".
    // This is not part of the Monad pattern itself, but it is how you extract the value
    // to leave the monad and return to the imperative world.
    // Typically used at the boundary to convert into a public-facing output (HTTP response, UI state, etc.).
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

### Unwrap at the boundary
> **Boundary:** the point where your code meets the outside world. Parse/refine inputs, run your logic, then translate the outcome into public outputs.
> Use `Match` at the boundary to convert an internal `Result` into `DTO`s/status codes/`ProblemDetails`/UI state. Don’t serialize `Result` directly—clients will start depending on its internal shape.
> Don’t ignore returned `Result` values—use analyzers to enforce this.[^unused-result]

```csharp
Result<int, string> result = Result<int, string>.Ok(42);

string output = result.Match(
    ok:  value => $"Success: {value}",
    err: error => $"Error: {error}"
);
```

#### Why you shouldn’t serialize `Result`
Don’t serialize `Result` directly.[^no-serialize][^serializer-aside] It leaks internal representation into your public contract. `Match` it into `DTO`s/status codes/`ProblemDetails` instead.

Many `Result` implementations expose `Value`/`Error` (and flags like `IsSuccess`) as public properties. A generic serializer will happily turn that internal shape into your public API—it just sees public properties and emits them (often with a camelCase naming policy), e.g.:

```json
{
  "isSuccess": true,
  "isFailure": false,
  "error": null,
  "value": { "id": 123, "isActive": false }
}
```

That wrapper is awkward, and it’s also brittle: now your public contract includes `isSuccess`/`isFailure` and your internal error/value shape. Unwrap at the boundary with `Match`, and return something that’s meant to be public (`DTO`s, status codes, `ProblemDetails`, etc.).

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

### Async: the `Task<Result<...>>` nesting weirdness

In modern .NET apps, most `I/O` APIs follow the Task-based async pattern (`Task` / `Task<T>`). This creates a "wrapping problem": your return types become `Task<Result<User, Error>>`.

Think of `await` as C#'s built-in "Do Notation" for the `Task` monad. Just as `Bind` unwraps the `Result` to get to the value, `await` unwraps the `Task` to get to the value.[^task-monad]

The friction happens when you stack them. If you try to mix the `Task` monad (`await`ing) and the `Result` monad (failure handling), you end up needing to `await` manually before every step—and you can't just `await` your way out of the structure, because `await` unwraps the `Task`, not the `Result`. This brings back the indentation you tried to kill.

### Async: keep the pipeline readable
If you need async + `Result` composition, don’t hand-roll helpers. Use a library that provides **async extensions** (often `Bind`/`Map` overloads for `Task<Result<...>>`; some libraries also expose `BindAsync`/`MapAsync`):
[^rakes]

- **[CSharpFunctionalExtensions](https://github.com/vkhorikov/CSharpFunctionalExtensions)**: Closest to the code in this post.
- **[LanguageExt](https://github.com/louthy/language-ext)**: A comprehensive library enforcing strict functional patterns.
- **[FluentResults](https://github.com/altmann/FluentResults)**: Object-oriented features.

With a library, the async pipeline stays linear.[^async-pseudocode]

Assume we have a method `ParseIdAsync(string input)` that returns `Task<Result<int, Error>>` and `FindUserAsync(int id)` that returns `Task<Result<User, Error>>`.

```csharp
private static Task<Result<User, Error>> DeactivateDecisionAsync(User user) =>
    Task.FromResult(DeactivateDecision(user));

public Task<Result<User, Error>> DeactivateUserAsync(string inputId) =>
    ParseIdAsync(inputId)
        .Bind(FindUserAsync)
        .Bind(DeactivateDecisionAsync);
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
[^try-catch]: A single big `try/catch` reduces noise, but it catches too broadly or loses step-specific failure reasons.
[^rop]: Scott Wlaschin, [Railway Oriented Programming](https://fsharpforfunandprofit.com/rop/).
[^always-valid]: Vladimir Khorikov, [Always valid vs not always valid domain model](https://enterprisecraftsmanship.com/posts/always-valid-vs-not-always-valid-domain-model/).
[^no-serialize]: FluentResults Wiki, [Returning Result Objects from ASP.NET Core Controller](https://github.com/altmann/FluentResults/wiki/Returning-Result-Objects-from-ASP.NET-Core-Controller).
[^unused-result]: C# allows ignoring return values, so a `Result` can be silently dropped. `exceptions` “force” handling by crashing; with `Result`, use a Roslyn analyzer to flag unused `Result`s (ideally as an error) so “oops” becomes a compile-time failure instead of a runtime crash.
[^implicit-conversions]: Some libraries add `implicit operator` conversions so you can `return value;` or `return error;` instead of writing `Result.Ok(...)`/`Result.Fail(...)`. This post avoids that because it can make it less obvious what is (and isn’t) a `Result`.
[^serializer-aside]: A generic serializer is like a toddler with a marker: it will eagerly “help” by drawing *every property it can reach* onto your public API.
[^either-bias]: Most `Either`/`Result` APIs are right-/success-biased: `Map`/`Bind` operate on the success branch and propagate the error branch unchanged. If you’re using an `Either` type, double-check which side your library treats as “success.”
[^async-pseudocode]: The snippet below assumes a library that provides async extensions/combinators (e.g., `Bind` on `Task<Result<...>>`). The teaching `Result` type above does not provide these by itself.[^either-bias]
[^rakes]: The library authors have already stepped on the rakes here so you don’t have to.
[^task-monad]: `Task<T>` **is** a monad (specifically the "Promise" or "Future" monad). It manages the "latency" and "concurrency" effects. While it has side effects (scheduling/timing), it follows the exact same structural laws as `Result` or `List`. See Stephen Toub, [Tasks, Monads, and LINQ](https://devblogs.microsoft.com/pfxteam/tasks-monads-and-linq/).
