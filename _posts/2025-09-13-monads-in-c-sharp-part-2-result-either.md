---
title: "Monads in C# (Part 2): Result"
date: 2025-09-13
description: "Build a small Result type in C# and use Map/Bind/Match to compose fail-fast workflows with explicit errors."
---

**Previously in the series**: [List is a monad (part 1)](https://alexyorke.github.io/2025/06/29/a-list-is-a-monad/)

> _Note_: This post was substantially rewritten on 2025-12-21.

In **Part 1**, we used `List<T>` to contrast `Map` vs `flatMap`, and built `Maybe<T>` to chain optional steps.

The Result monad allows you to represent a computation's outcome as success or failure and to sequence computations so failures propagate until handled.

This transforms error handling from implicit control flow into an explicit return value. This allows errors to flow linearly, avoiding implicit throws and verbose defensive checking.

Think of it like `Maybe`, but the negative branch carries data: while `Maybe` represents *absence* (`None`), `Result` represents *failure* (`Error`).

#### The Problem: Explicitness vs. Readability

In everyday C#, you tend to end up in one of two styles: rely on **Implicit Control Flow** (exceptions) or write **Verbose Validation** (guard clauses).

**Option A: Implicit Control Flow (Exceptions)**
This code is concise, but the method signature doesn't tell you what can go wrong. `DeactivateUser` returns `void`, yet it can throw `FormatException`, `NullReferenceException`, or a custom `DomainException`.

```csharp
// The signature implies success, hiding the failure modes.
// To use this safely, the caller relies on documentation or try/catch blocks.
public void DeactivateUser(string inputId)
{
    // If parsing fails, the stack unwinds immediately.
    int id = int.Parse(inputId);

    var user = repo.Find(id);

    // Flow control is handled via exceptions rather than return values.
    if (!user.IsActive)
        throw new Exception("User already inactive");

    user.IsActive = false;
    repo.Save(user);
}
```

In a small snippet, the throwing lines are obvious. In a real service, they’re not. Exceptions can come from almost anywhere (parsing, mapping, I/O, nulls), and once you start composing steps you end up wrapping a lot of code in `try/catch` scaffolding.

**Option B: Explicit Validation (Guard Clauses)**
If you want to keep exceptions for truly exceptional cases, you end up with guard clauses and early returns. The control flow stays linear and explicit, but the validation checks get interleaved with the work.

```csharp
// The "Happy Path" is interleaved with validation checks.
public string DeactivateUser(string inputId)
{
    if (!int.TryParse(inputId, out var id))
        return "Invalid ID";

    var user = repo.Find(id);
    // Note: 'null' implies absence, but lacks context (e.g., DB Timeout vs. Missing Record).
    if (user is null) 
        return "User not found";

    if (!user.IsActive)
        return "User already inactive";

    // The state change occurs only after all guards pass.
    user.IsActive = false;
    repo.Save(user);
    return "Success";
}
```

At this point you either drop the reason (return `bool`) or invent a convention (tuples, out-params, strings). `Result` gives that convention a name and a shape.

#### The Solution: The Control Flow Spectrum

The `Result` type provides a middle ground between ignoring absence (Nullable) and aborting execution (Exception). It allows us to model **Recoverable Failure** as a first-class value.

> **Concept Check: The Control Flow Spectrum**
> 
> **1. Result (`Result<T, E>`) → "Expected failure"**
> *   **Use when:** An operation can fail as part of normal business logic (e.g., "User Not Found" or "Validation Failed").
> *   **Control Flow:** Linear & Composable. You chain operations without `try/catch` blocks.
> 
> **2. Exception → "Panic / Abort"**
> *   **Use when:** Something unexpected happened and you can't continue locally (e.g., OutOfMemory, bad config).
> *   **Control Flow:** **Jump.** It rips through the stack until caught.

> **Note on Nullable Types (`T?`)**
> 
> C#'s nullable reference types (`string?`, etc.) primarily help the **compiler** detect potential `NullReferenceException`s. They assist in modeling **anticipated absence**, i.e., situations where a value might legitimately be missing (like an optional middle name), or an API might return `null` when a record isn't found. The compiler provides warnings if you don't handle these potential nulls, offering a layer of safety.
> 
> Nullable reference types are related, but they solve a different problem:
> *   Focus on **data absence** (static state), not **operation failure** (action outcome).
> *   Primary protection is **compile-time analysis**, not runtime error propagation.
> *   Handled with explicit checks (`if (value is null)`) or operators (`??`), rather than chaining like `Bind`. `Result` gives you that kind of composition for **expected failures**.

Now you can rewrite Option B as a pipeline: each step either produces the next value or stops with an error.

```csharp
// Declarative: The logic flows in a single pipeline.
// No 'if' statements required between steps.
Result<User, Error> result =
    ParseId(inputId)
        .Bind(FindUser)
        .Bind(Deactivate);

// Handle the final outcome in one place
string message = result.Match(
    ok:  _ => "User deactivated",
    err: e => $"Deactivate failed: {e.Code} - {e.Message}");
```

> **Note:** `Result` is designed to **short-circuit** (stop at the first error). If you need to **accumulate** multiple errors (e.g., validating a form where you want to show all missing fields at once), use an *Accumulating Validation* type instead.

### Implementing Result
Here’s a small teaching implementation. If you’re shipping this, use a library instead (e.g., *LanguageExt*, *CSharpFunctionalExtensions*, or *FluentResults*).

```csharp
public sealed class Result<TSuccess, TError>
{
    // The state is binary: it contains EITHER a value OR an error, never both.
    private readonly TSuccess? _value;
    private readonly TError? _error;

    public bool IsSuccess { get; }
    public bool IsFailure => !IsSuccess;

    // Internal constructor ensures we never create an invalid state.
    private Result(TSuccess? value, TError? error, bool isSuccess)
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

    // MAP: Transforms the data if successful. If the Result is a Failure, this is skipped entirely.
    // The "Magic": If this Result is already a Failure, the function 'f' never runs,
    // and the existing error is passed along.
    public Result<U, TError> Map<U>(Func<TSuccess, U> f)
    {
        if (IsSuccess)
        {
            return Result<U, TError>.Ok(f(_value!));
        }

        return Result<U, TError>.Fail(_error!);
    }

    // BIND: Chains an operation that *also* returns a Result.
    // This is the "Railway Switch": if the previous step failed, we stop immediately.
    // Note: the function 'f' provides the *new* success OR the *new* failure.
    public Result<U, TError> Bind<U>(Func<TSuccess, Result<U, TError>> f)
    {
        if (IsSuccess)
        {
            return f(_value!);
        }

        return Result<U, TError>.Fail(_error!);
    }

    // MATCH: Unwraps the final value.
    // This forces you to handle both cases to get the data out.
    // Typically used at the API boundary to convert to HTTP 200/400.
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

### Unwrapping with `Match`
Once the pipeline is complete, use `Match` to convert the internal `Result` back into a concrete value (like an HTTP response or a console message).

```csharp
Result<int, Error> result = Result<int, Error>.Ok(42);

string output = result.Match(
    ok:  value => $"Success: {value}",
    err: error => $"Error: {error.Code}"
);
```

### Key Benefits
Using `Result` provides structural advantages over exceptions or sentinel values:
*   **Explicit Signatures:** The return type `Result<User, Error>` clearly indicates that failure is a possible outcome, unlike `User` which implies guaranteed success.
*   **Type Safety:** It removes the ambiguity of "Magic Numbers" (e.g., returning `-1`) or `null` checks.
*   **Testability:** Unit tests can assert on clear `IsSuccess`/`IsFailure` properties rather than relying on `ExpectedException` attributes.

### Scope & Limitations
The `Result` pattern is optimized for **Domain Logic** (expected failures). It complements, rather than replaces, standard Exceptions in specific scenarios:

1.  **Infrastructure:** Unexpected failures (Database offline, OutOfMemory) are best handled by global middleware. These should remain Exceptions rather than being wrapped in `Result`.
2.  **Bugs:** Precondition violations (e.g., passing `null` to a method that requires a value) indicate a bug in the code, not a business rule failure. Standard exceptions like `ArgumentNullException` are appropriate here.
3.  **Accumulation:** `Bind` stops at the first error. If you need to collect *all* validation errors (e.g., checking 5 form fields and reporting all mistakes), use a **Validation** structure designed for accumulation rather than the short-circuiting behavior of `Result`.

### Putting it together: Functional core, imperative shell
#### Example: Deactivating a user
We want to deactivate a user given a user's `id` (a **string**) from an HTTP request.[^id]

We'll use a simple custom error payload in the examples below (this is **not** part of `Result` itself):

```csharp
public record Error(string Code, string Message);
```

Keep the workflow pure, then exit once at the boundary.

```csharp
public sealed class UserService
{
    private readonly IUserRepo _repo;
    public UserService(IUserRepo repo)
    {
        _repo = repo;
    }

    // Pure logic: Parse -> Find -> Deactivate -> Return Result
    public Result<User, Error> DeactivateUser(string inputId)
    {
        return ParseId(inputId)
            .Bind(FindUser)
            .Bind(Deactivate);
    }

    // Boundary: unwrap and perform effects (persistence, logging, etc.)
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

    // --- Steps ---

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

    private static Result<User, Error> Deactivate(User user)
    {
        if (!user.IsActive)
            return Result<User, Error>.Fail(new Error("Domain", "User is already inactive"));

        // Domain Mutation: valid here because the 'Save' hasn't happened yet.
        user.IsActive = false;
        return Result<User, Error>.Ok(user);
    }
}
```

This enforces the **"Functional Core, Imperative Shell"** architecture:
1.  **Read/Compute:** Done in the `Result` pipeline (`DeactivateUser`).
2.  **Write/Side-Effect:** Done in the `Match` block (`HandleDeactivateRequest`).

### Exiting the Monad (The API Boundary)
Treat `Result<TSuccess, TError>` as internal plumbing.
At the **Edge** of your application (API Controller, CLI, UI View Model), unwrap it with `Match`.

This keeps your internal domain logic decoupled from your HTTP contract.

Never return `Result<...>` directly to a generic JSON serializer. Unwrap it into a `ProblemDetails` (for failure) or a specific DTO (for success) so your public API remains stable even if your internal error types change.

#### The "Russian Doll" Risk
If you return a `Result` directly from a Controller, you leak implementation details and create awkward JSON wrappers:

```json
{
  "isSuccess": true,
  "isFailure": false,
  "error": null,
  "value": { "id": 123, "isActive": false }
}
```

Always unwrap at the boundary using `Match` to return standard HTTP responses or clean DTOs.

### The Async Reality (Async composition friction)

In modern C#, almost all I/O is asynchronous and returns `Task<T>`. This creates a "wrapping problem": your return types become `Task<Result<User, Error>>`.

One way to think about it: `Task<T>` composes too. `await` + projection looks like `Map`, and `await` + returning another task looks like `Bind`.[^task-monad]

The friction happens when you stack them. If you try to mix the `Task` monad (awaiting) and the `Result` monad (failure handling), you end up needing to `await` manually before every step—and you can't just `await` your way out of the structure, because `await` unwraps the `Task`, not the `Result`. This brings back the indentation you tried to kill.

### How to fix it (Combinators)
If you need async + `Result` composition, don’t hand-roll helpers. Use a library that provides `BindAsync` (sometimes called `SelectManyAsync`):

- **CSharpFunctionalExtensions**: Closest to the code in this post.
- **LanguageExt**: Strict functional style ("Haskell for C#").
- **FluentResults**: Object-oriented features.

> **Either bias note:** Some libraries model `Either`/`Result` as left-biased or right-biased; a few are "unbiased" (neither side is preferred). Check your library docs to know which branch `Map`/`Bind` operates on by default.

With a library, the async pipeline stays linear:

```csharp
// Libraries providing "BindAsync" handle the Task wrapper for you:
public Task<Result<User, Error>> DeactivateUser(string inputId) =>
    ParseIdAsync(inputId)           // Task<Result<int, Error>>
        .BindAsync(FindUserAsync)   // Await task, check Result, then run Find
        .BindAsync(DeactivateAsync);
```

### Testing Strategies
Testing `Result` is cleaner than testing Exceptions because you don't need `Assert.Throws`.

In a real codebase, you might add a small helper to "peek" inside a `Result` in tests. For this post, sticking to the public API is fine.

If your `Result` type keeps its internals private, use `Match` to unwrap the error for assertion. In a unit test, entering the success branch when you expected failure is a test failure, so throw immediately.

Also: don't stop at "it failed"—assert the *kind* of failure (code/message/type). Otherwise, the wrong failure can sneak in and your test still passes.

```csharp
[Fact]
public void DeactivateUser_ReturnsFailure_WhenUserNotFound()
{
    // Arrange
    var repo = new InMemoryUserRepo(); // empty
    var service = new UserService(repo);

    // Act
    var result = service.DeactivateUser("123");

    // Assert: Check State
    Assert.True(result.IsFailure);
    
    // Assert: Check Reason (using Match to inspect the private error)
    var error = result.Match(
        ok: _ => throw new Exception("Expected failure but operation succeeded!"),
        err: e => e
    );
    
    Assert.Equal("NotFound", error.Code);
}
```

### Wrap-up

`Result` keeps “expected failure” in-band, as data.

1.  **Chain** with `Map`/`Bind`.
2.  **Handle** `Task<Result<...>>` using async combinators.
3.  **Decide** once at the edge with `Match`.

**Next in the series**: [Monads in C# (Part 3): The Reader Monad](https://alexyorke.github.io/2025/12/20/monads-in-c-sharp-part-3-the-reader-monad/)

[^id]: In real systems, an identifier is often better modeled as a domain type (e.g., `UserId`) rather than a bare number. This post uses `string` at the boundary and parses to `int` to keep the example focused on `Result` composition.
[^task-monad]: `Task<T>` isn’t strictly a pure monad because it triggers execution immediately (it is "Hot") and caches results, but it obeys the laws well enough to model it as one for control flow.
