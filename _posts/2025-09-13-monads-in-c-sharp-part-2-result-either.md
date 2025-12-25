---
title: "Monads in C# (Part 2): Result"
date: 2025-09-13
description: "Build a small Result type in C# and use Map/Bind/Match to compose fail-fast workflows with explicit errors (plus notes on async and API boundaries)."
---

**Previously in the series**: [List is a monad (part 1)](https://alexyorke.github.io/2025/06/29/a-list-is-a-monad/)

> _Note_: This post was substantially rewritten on 2025-12-21.

In **Part 1**, we used `List<T>` to contrast `Map` vs `flatMap`, and built `Maybe<T>` to chain optional steps. Now, we model **fallible** outcomes with a reason: `Result<TSuccess, TError>`.

Think of `Result` like `Maybe`, but the negative branch carries data. While `Maybe` represents *absence* (`None`), `Result` represents *failure* (`Error`).

The Result monad allows you to represent a computation's outcome as success or failure and to sequence computations so failures propagate until handled. This saves you from **"Defensive Coding Noise"**—where your business logic is interrupted every other line by error checks. It also prevents **Hidden Control Flow**, where Exceptions act like invisible `GOTO` statements that force the caller to guess what might go wrong.

> **Concept Check: Result vs. Nullable (`T?`)**
> 
> Use `T?` when a value implies **Absence** and you don't care why (e.g., a user's optional middle name).
> 
> Use `Result` when a value implies **Failure** and the reason matters. If `FindUser(id)` returns `null`, you don't know if the ID was malformed, the user was deleted, or the database timed out. `Result` makes that distinction explicit.

#### The Problem: The "Honesty" vs. "Clarity" Trade-off

In traditional C#, we usually have to choose between code that is **clean but dishonest** (Exceptions) or **honest but noisy** (Guard Clauses).

**Option A: The Exception Trap (Clean, but Dishonest)**
This code is easy to read, but the signature lies. `DeactivateUser` claims to return `void`, but it might actually throw `FormatException`, `NullReferenceException`, or a custom `DomainException`.

```csharp
// The signature hides the complexity.
// To use this safely, the caller MUST wrap it in a try/catch.
public void DeactivateUser(string inputId)
{
    // If parsing fails, the app blows up.
    int id = int.Parse(inputId);

    // If user is null, the app blows up later.
    var user = repo.Find(id);

    // This looks like logic, but it's implicitly controlling flow via exceptions.
    if (!user.IsActive)
        throw new Exception("User already inactive");

    user.IsActive = false;
    repo.Save(user);
}
```

**Option B: The Defensive approach (Honest, but Noisy)**
To avoid exceptions, we use "Guard Clauses." This is safer, but now 80% of our code is error checking, and the actual business value (deactivating the user) is buried at the bottom.

```csharp
// Imperative: The "Happy Path" is fragmented by error checks.
public string DeactivateUser(string inputId)
{
    if (!int.TryParse(inputId, out var id))
        return "Invalid ID";

    var user = repo.Find(id);
    if (user is null)
        return "User not found";

    if (!user.IsActive)
        return "User already inactive";

    // Finally, the actual work happens here.
    user.IsActive = false;
    repo.Save(user);
    return "Success";
}
```

#### The Solution: Chaining
`Result` sequences these steps using `Bind`. This keeps the "happy path" readable: the first failure short-circuits the chain, and that error flows to the end automatically.

```csharp
// Declarative: The logic flows in one uninterrupted pipeline.
// No 'if' statements to break your reading flow.
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

#### Example: Deactivating a user
We want to deactivate a user given an `id` **string** from an HTTP request.[^id]

### Why bother?
Using `Result` over exceptions or `bool` returns has specific benefits:
*   **Honest Signatures:** You don't have to read the source code to know a method can fail.
*   **No Sentinels:** No more `return null` or `-1` to represent errors.
*   **Testability:** Tests assert on `Ok` vs `Fail` states rather than `ExpectedException` attributes.

### When `Result` is the wrong tool
`Result` is for **domain logic** failures. It is not a silver bullet.

1.  **Infrastructure:** If the DB is down or you run out of memory, let the exception bubble to your middleware. Do not catch generic exceptions just to wrap them in `Result.Fail`.
2.  **Bugs:** If a method receives a `null` argument that should never be null, throw `ArgumentNullException`. That is a bug, not a business outcome.
3.  **Accumulation:** As mentioned earlier, `Bind` short-circuits. For form validation (where you want 10 errors, not just the first one), you need "Applicative Validation," not monadic binding.

### Implementing Result
Here is a teaching implementation. (In production, consider a battle-tested library like *LanguageExt*, *CSharpFunctionalExtensions*, or *FluentResults*.)

```csharp
// Structured error type (instead of just a string).
public record Error(string Code, string Message);

public sealed class Result<TSuccess, TError>
{
    // Invariant:
    // - If IsSuccess == true, _value is meaningful and _error is unused.
    // - If IsSuccess == false, _error is meaningful and _value is unused.
    private readonly TSuccess? _value;
    private readonly TError? _error;

    public bool IsSuccess { get; }
    public bool IsFailure
    {
        get { return !IsSuccess; }
    }

    // Why a 3-parameter constructor?
    //
    // A tempting design is to have two private constructors:
    //     Result(TSuccess value) and Result(TError error)
    //
    // But if TSuccess and TError are the same type (e.g., Result<int, int>),
    // those overloads collide and calls become ambiguous. The explicit isSuccess
    // flag makes the internal representation unambiguous.
    private Result(TSuccess? value, TError? error, bool isSuccess)
    {
        IsSuccess = isSuccess;
        _value = value;
        _error = error;
    }

    public static Result<TSuccess, TError> Ok(TSuccess value)
    {
        // We store default(TError) in the unused slot.
        return new Result<TSuccess, TError>(
            value: value,
            error: default(TError),
            isSuccess: true);
    }

    public static Result<TSuccess, TError> Fail(TError error)
    {
        // We store default(TSuccess) in the unused slot.
        return new Result<TSuccess, TError>(
            value: default(TSuccess),
            error: error,
            isSuccess: false);
    }

    // Functor: Transform the inner value (success branch only).
    // Common pitfall: Map does not run on failures; it preserves the error untouched.
    public Result<U, TError> Map<U>(Func<TSuccess, U> f)
    {
        if (IsSuccess)
        {
            return Result<U, TError>.Ok(f(_value));
        }

        return Result<U, TError>.Fail(_error);
    }

    // Monad: Chain a dependent operation that might fail (short-circuits on the first failure).
    public Result<U, TError> Bind<U>(Func<TSuccess, Result<U, TError>> f)
    {
        if (IsSuccess)
        {
            return f(_value);
        }

        return Result<U, TError>.Fail(_error);
    }

    // Match: Leave the monad by turning a Result into a "plain" value.
    // This is typically used at the boundary (API/UI/CLI) to decide what to do next.
    public TResult Match<TResult>(Func<TSuccess, TResult> ok, Func<TError, TResult> err)
    {
        if (IsSuccess)
        {
            return ok(_value);
        }

        return err(_error);
    }
}
```

### Unwrapping with `Match`
You can chain as long as you like, but eventually, the outside world needs a result. Use `Match` at your application boundary (e.g., API Endpoint or UI Logic).

```csharp
Result<int, Error> result = Result<int, Error>.Ok(42);

string output = result.Match(
    ok:  value => $"Success: {value}",
    err: error => $"Error: {error.Code}"
);
```
### Putting it together: Functional core, imperative shell
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

    // The Domain Pipeline (The Functional Core)
    // Pure logic: Parse -> Find -> Deactivate -> Return Result
    public Result<User, Error> DeactivateUser(string inputId) =>
        ParseId(inputId)
            .Bind(FindUser)
            .Bind(Deactivate);

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

### The Async Reality (Async composition friction)

In modern C#, almost all I/O is asynchronous and returns `Task<T>`. This creates a "wrapping problem": your return types become `Task<Result<User, Error>>`.

A useful mental model: `Task<T>` composes too! `await` + projection is basically `Map`, and `await` + returning another task is basically `Bind`.[^task-monad]

The friction happens when you stack them. If you try to mix the `Task` monad (awaiting) and the `Result` monad (failure handling), you end up needing to `await` manually before every step—and you can't just `await` your way out of the structure, because `await` unwraps the `Task`, not the `Result`. This brings back the indentation you tried to kill.

### How to fix it (Combinators)
If you need async + `Result` composition, do not hand-roll helpers. Use a library that provides `BindAsync` (sometimes called `SelectManyAsync`):

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

### Testing Strategies
Testing `Result` is cleaner than testing Exceptions because you don't need `Assert.Throws`.

In production codebases, tests often benefit from small "peek" helpers or custom assertion methods, but sticking to the public API is fine for this article.

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

`Result` is just a way to keep “expected failure” in-band, as data.

1.  **Chain** with `Map`/`Bind`.
2.  **Handle** `Task<Result<...>>` using async combinators.
3.  **Decide** once at the edge with `Match`.

**Next in the series**: [Monads in C# (Part 3): The Reader Monad](https://alexyorke.github.io/2025/12/20/monads-in-c-sharp-part-3-the-reader-monad/)

[^id]: In real systems, an identifier is often better modeled as a domain type (e.g., `UserId`) rather than a bare number. This post uses `string` at the boundary and parses to `int` to keep the example focused on `Result` composition.
[^task-monad]: `Task<T>` isn’t strictly a pure monad because it triggers execution immediately (it is "Hot") and caches results, but it obeys the laws well enough to model it as one for control flow.
