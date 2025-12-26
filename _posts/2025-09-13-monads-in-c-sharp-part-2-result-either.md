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

In a small snippet, the throw sites are obvious. In a real service, exceptions can come from almost anywhere (parsing, mapping, I/O, nulls), so once you start composing steps you end up wrapping a lot of code in `try/catch` scaffolding.

**Option B: Explicit Validation (Guard Clauses)**
If you want to keep exceptions for truly exceptional cases, you end up with guard clauses and early returns. The control flow stays linear and explicit, but the validation checks get interleaved with the work.

> **Aside:** Guard clauses are the bouncer at the door: efficient, reliable… and absolutely uninterested in your “happy path” skipping the line.

```csharp
// The "Happy Path" is interleaved with validation checks.
public string DeactivateUser(string inputId)
{
    if (!int.TryParse(inputId, out var id))
        return "Invalid ID";

    var user = repo.Find(id);
    // Note: 'null' implies absence, but lacks context (e.g., DB Timeout vs. Missing Record),
    // and it has a habit of showing up uninvited.
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

> **Aside:** Nullable reference types are the compiler’s polite cough: “ahem… you sure about that?”

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
Here’s a small teaching implementation. Don’t use it in production; if you’re shipping this, use a library instead (e.g., *LanguageExt*, *CSharpFunctionalExtensions*, or *FluentResults*).

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
    // The "Magic Trick": If this Result is already a Failure, the function 'f' never runs,
    // and the existing error is passed along (which is great, because failing is plenty of work already).
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

### Handling the Final Outcome
At the boundary, use Match to map your internal Result into a public-facing output (an HTTP response, a console message, or a UI state).

> **Concept Check: Core, Shell, and the Boundary**
> In a “Functional Core, Imperative Shell” design, the **core** is pure, deterministic business logic over immutable data. The **shell** is the integration layer that performs I/O (HTTP, files, DB, UI) and coordinates the app’s runtime concerns.
>
> The **boundary** is where you:
>
> 1. **Parse/refine** messy inputs into well-typed domain data (so the core doesn’t accept `unknown` / raw strings / half-valid shapes), then
> 2. call the core to **produce a decision**, and finally
> 3. **act** on that decision with side effects (persist, return a response, update UI).
>
> Examples of the shell in different hosts:
>
> * **Web API:** a controller parses the request, calls the core, and maps the decision to an HTTP response.
> * **CLI:** `Main` parses args, calls the core, prints output, and sets an exit code.
> * **Desktop/Mobile:** a ViewModel parses inputs/events, calls the core, and maps the decision into UI state.
>
> Keep dependencies flowing inward: the shell depends on the core, not the other way around. Unwrap `Result<TSuccess, TError>` at the boundary (e.g., with `Match`) and return types meant to be public—DTOs, `ProblemDetails`, strings, status codes, or UI state.

Keep Result on the inside. At the boundary, Match it into DTOs/status codes/UI state instead of returning it directly.

```csharp
Result<int, string> result = Result<int, string>.Ok(42);

// Match ensures every branch is handled before the data leaves your logic
string output = result.Match(
    ok:  value => $"Success: {value}",
    err: error => $"Error: {error}"
);
```

#### Why Serialization Breaks the Pattern
A major risk of the `Result` pattern is the temptation to return the object directly to a generic JSON serializer. When you do this, you lose the "Making Illegal States Unrepresentable" guarantee.[^illegal-states]

> **Aside:** A generic serializer is like a toddler with a marker: it will eagerly “help” by drawing *every property it can reach* onto your public API.

In your C# code, the private constructor enforces the invariant (you can’t have both value and error at the same time). A generic serializer doesn’t know (or care) about that—it just sees properties and prints them:

```json
{
  "isSuccess": true,
  "isFailure": false,
  "error": null,
  "value": { "id": 123, "isActive": false }
}
```

That wrapper is awkward, and it’s also brittle: now your public contract includes `isSuccess`/`isFailure` and your internal error/value shape. Unwrap at the boundary with `Match`, and return something that’s meant to be public (DTOs, status codes, `ProblemDetails`, etc.).

### Key Benefits
What do you get for returning `Result` instead of throwing or using sentinels?
*   **Explicit Signatures:** `Result<User, Error>` tells you up front that failure is on the table.
*   **Fewer ad-hoc conventions:** No `-1`, no `null`, no “special string means error.”
*   **Testability:** Tests can assert on `IsSuccess`/`IsFailure` and inspect the error without `Assert.Throws`.

### Scope & Limitations
`Result` works best for **domain logic**: failures you expect and want to handle. It doesn’t replace exceptions; it just keeps them in their lane.

1.  **Infrastructure:** For technical failures (DB/network outages, timeouts, unexpected I/O errors), exceptions handled at the boundary (middleware/logging/global handlers) are often a good fit.
2.  **Bugs:** Violated preconditions are programmer errors—throw (`ArgumentNullException`, `ArgumentException`, etc.) rather than returning a domain `Result`.
3.  **Accumulation:** `Bind` stops at the first error. If you need to collect *all* validation errors, use a validation type that accumulates errors instead of short-circuiting.

### Putting it together: Functional core, imperative shell
#### Example: Deactivating a user
We want to deactivate a user given an `id` from an HTTP request (received as a **string**, parsed to an `int`).[^id]

We'll use a simple custom error payload in the examples below (this is **not** part of `Result` itself):

```csharp
public record Error(string Code, string Message);
```

Keep decision logic separate from I/O: compute first, then perform effects once at the boundary.

```csharp
public sealed class UserService
{
    private readonly IUserRepo _repo;
    public UserService(IUserRepo repo)
    {
        _repo = repo;
    }

    // Orchestration (shell): Parse -> Load -> Decide
    public Result<User, Error> DeactivateUser(string inputId)
    {
        return ParseId(inputId)
            .Bind(FindUser)
            .Bind(DeactivateDecision);
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

    // Core decision: compute an updated user (no I/O).
    private static Result<User, Error> DeactivateDecision(User user)
    {
        if (!user.IsActive)
            return Result<User, Error>.Fail(new Error("Domain", "User is already inactive"));

        // Prefer immutable data flow (e.g., records). Persistence happens at the boundary.
        return Result<User, Error>.Ok(user with { IsActive = false });
    }
}
```

This enforces the **"Functional Core, Imperative Shell"** architecture:
1.  **Orchestrate (parse + load + decide):** Done in the `Result` pipeline (`DeactivateUser`).
2.  **Act (persist + return output):** Done in the `Match` block (`HandleDeactivateRequest`).

### The Async Reality (Async composition friction)

In modern C#, almost all I/O is asynchronous and returns `Task<T>`. This creates a "wrapping problem": your return types become `Task<Result<User, Error>>`.

One way to think about it: `Task<T>` composes too. `await` + projection looks like `Map`, and `await` + returning another task looks like `Bind`.[^task-monad]

The friction happens when you stack them. If you try to mix the `Task` monad (awaiting) and the `Result` monad (failure handling), you end up needing to `await` manually before every step—and you can't just `await` your way out of the structure, because `await` unwraps the `Task`, not the `Result`. This brings back the indentation you tried to kill.

### How to fix it (Combinators)
If you need async + `Result` composition, don’t hand-roll helpers. Use a library that provides `BindAsync` (sometimes called `SelectManyAsync`):

> **Aside:** The library authors have already stepped on the rakes here so you don’t have to.

- **CSharpFunctionalExtensions**: Closest to the code in this post.
- **LanguageExt**: Strict functional style ("Haskell for C#").
- **FluentResults**: Object-oriented features.

> **Either bias note:** Some libraries model `Either`/`Result` as left-biased or right-biased; a few are "unbiased" (neither side is preferred). Check your library docs to know which branch `Map`/`Bind` operates on by default.

With a library, the async pipeline stays linear:

```csharp
// Libraries providing "BindAsync" handle the Task wrapper for you:
public Task<Result<User, Error>> DeactivateUser(string inputId) =>
    ParseIdAsync(inputId)           // Task<Result<int, Error>>
        .BindAsync(FindUserAsync)   // Orchestration: await task, check Result, then load
        .BindAsync(DeactivateDecisionAsync);
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
[^illegal-states]: This is an instance of **"making illegal states unrepresentable"**: designing your types so invalid states can’t be constructed in the first place. In this post, the private `Result` constructor is the mechanism. Yaron Minsky popularized the phrase in his talk **"Effective ML"** (OCaml syntax, but broadly applicable): `https://www.youtube.com/watch?v=-J8YyfrSwTk`.
