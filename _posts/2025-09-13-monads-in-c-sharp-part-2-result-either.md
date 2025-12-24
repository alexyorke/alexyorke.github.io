---

title: "Monads in C# (Part 2): Result"
date: 2025-09-13
description: "Build a small Result type in C# and use Map/Bind/Match to compose fail-fast workflows with explicit errors (plus notes on async and API boundaries)."
---

**Previously in the series**: [List is a monad (part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/)

> _Note_: This post was substantially rewritten on 2025-12-21.

In Part 1 you built `Maybe` and used `Bind` (aka `FlatMap`) to chain optional steps. This part keeps that shape but lets the "no value" branch carry a reason via `Result<TSuccess, TError>`.

Concretely, `Result` lets you write a multi-step workflow where each step can fail, without turning the code into an `if` ladder or a pile of `try`/`catch` for expected outcomes:

```csharp
Result<User, Error> result =
    ParseId(inputId)
        .Bind(FindUser)
        .Bind(Deactivate);

string message = result.Match(
    ok:  _ => "User deactivated",
    err: e => $"Deactivate failed: {e.Code} - {e.Message}");
```

If you think in `LINQ`: `Map` ≈ `Select`, `Bind`/`FlatMap` ≈ `SelectMany`. We’ll stick to method style here to keep focus on the flow rather than syntax.

> Terminology note (Either vs. Result):
> Result<TSuccess, TError> is a convention: it encodes “success vs. failure.”
> You’ll also see Either<L, R>, which encodes “one of two possibilities.” In some libraries, Either is right-biased, so Map/Bind compose the Right value and short-circuit on Left.
> If you use Either<TError, TSuccess>, it’s effectively the same workflow shape as Result<TSuccess, TError>.
> This post uses Result because the names “Success/Error” make the intended meaning hard to misread.

### Result: when “missing” needs a reason

`Maybe<T>` tells us whether a value exists. Sometimes, we need *why* it doesn’t exist. We keep the same straight‑line composition:

*   **Map**: transform the success value.
*   **Bind**: chain a function returning another `Result<...>`.
*   **Unit (Ok)**: The `Unit` operation (from Part 1) is implemented here as **`Ok`**. It lifts a raw value into the success branch.

   ...and add a **failure** branch that carries an error.

The key behavior: **Bind is fail-fast**. Once you hit a failure, downstream steps don’t run; the error flows through unchanged.

Think of it like:
*   `Ok(value)` -> like `Some(value)`
*   `Fail(error)` -> like `None()`, but with a reason

### Scenario: The "Deactivate User" Pipeline

We want to deactivate a user given a raw `id` **string** from an HTTP request. “Deactivate” here means marking the user inactive (e.g., setting `IsActive = false`) and persisting that change.[^id] We parse the raw string into our internal ID representation (an `int` in this post).

The steps are dependent:

1.  **Parse:** Parse the raw `string` into an `int`. (If this fails, we cannot proceed).
2.  **Find:** The user must exist in the database. (If missing, we cannot deactivate).
3.  **Business rule:** The user must currently be active. (If already inactive, it's a domain error).

> **Quick note: Result vs. `T?` (optional)**
>
> Use `T?` when a value might be missing and you don't care why.
>
> Example: A user's middle name. If it's null, it just doesn't exist. We don't need an error code explaining its absence.
>
> Use `Result<TSuccess, TError>` when a value is missing and it matters why.
>
> Example: Looking up a user by ID. If they are missing, is it `NotFound`, `PermissionDenied`, or `DatabaseError`? The error value tells you how to react.

These steps are **sequential**. Step 2 cannot run if Step 1 fails. `Result` models this fail-fast workflow. To motivate `Result`, let’s start with a few familiar C# implementations of this workflow.

### Why return a `Result` at all?
Returning a `Result<TSuccess, TError>` is a trade-off: you make failure explicit in the type system instead of hiding it in `null` values or the call stack.

- **Honest signatures**: `Result<User, Error>` tells callers “this can fail” up front, and gives them the *reason*.
- **Fewer invalid states**: you avoid “sentinel” failures like `null` where the signature claims a value exists but reality disagrees.
- **Predictable control flow**: expected failures become ordinary values instead of “GOTO-like” jumps via exceptions.
- **Composable pipelines**: once you have `Map`/`Bind`, you can reuse small steps (`ParseId`, `FindUser`, domain rules) without rewriting error plumbing at every call site.
- **Testability**: you assert on a returned value (`Ok`/`Fail`) instead of relying on thrown exceptions as the primary mechanism for domain outcomes.

### When NOT to use `Result`
`Result` is great for **expected, domain-level failures**. It’s a poor fit in a few common scenarios:

- **System Failures (The Database is Down):** Do not use `Result` for database connection failures, out-of-memory errors, or null references. These are exceptional system states. Returning `Result.Fail("DB_DOWN")` forces every caller to handle a catastrophe they cannot fix. Let these exceptions bubble up to global middleware.
- **Bugs (Invariant Violations):** If a method receives an argument that should be impossible (e.g., `UpdateUser(null)`), throw `ArgumentNullException`. That is a bug in the caller, not a domain outcome.
- **Hot Paths:** If you are processing 100k events/second, the allocation of `Result` objects (if implemented as classes) creates GC pressure. In strict performance contexts, `try/out` patterns or structs are preferable.
- **Validation that must accumulate errors**: if you want “email invalid **and** password weak” in one response, `Result`’s fail-fast monadic chaining is the wrong tool; prefer a validation/accumulator type.
- **Shotgun validation in the domain**: if every domain method accepts weak primitives (`string email`) and returns `Result` for basic format checks, you’re not modeling invariants—parse once at the boundary into strong types/value objects, then keep the core domain free of “is this string valid?” checks.
- **Side-effect-only chains** (`Result<Unit>` / `Result<void>`): chaining logging/metrics/email/cache writes via `Bind` often creates artificial sequencing and hides partial-success realities. Prefer doing effects at the boundary (or explicit orchestration patterns like jobs/sagas) rather than monadifying every void step.
- **Partial success / batch work**: if “process 100 items” can succeed for 95 and fail for 5, a single `Result<List<T>, E>` forces the wrong all-or-nothing semantics. Prefer a dedicated batch result type (successes + failures) or a list of per-item results.
- **Effect stacking / “transformer hell”**: if you end up drowning in `Task<Result<...>>` glue (and you’re not using a library that smooths it), the complexity may outweigh the benefits.

### Comparison: The Status Quo
Exceptions: Implicit control flow. Good for system crashes, bad for expected domain logic ("User not found").
Tuples (bool Success, string Error): Creates manual error propagation. You must check if (!success) return ... after every step. One missed check leads to bugs.
The strongest competitor in C# is the Try/Out Pattern:

```csharp
public static bool TryDeactivateUser(
    IUserRepo repo,
    string inputId,
    [System.Diagnostics.CodeAnalysis.NotNullWhen(true)] out User? user) // non-null when the method returns true
{
    if (int.TryParse(inputId, out int id)
        && repo.TryFind(id, out var found)
        && found.IsActive)
    {
        found.IsActive = false;
        repo.Save(found);
        user = found;
        return true;
    }

    // Assign the out parameter on the failure path (conventionally a default/null for reference types)
    user = null;
    return false;
}
```

This is idiomatic and can be quite efficient for low-level logic, and it composes nicely via short-circuiting.
The trade-off is that it **swallows the reason**.
If `TryDeactivate` returns `false`, was the ID format invalid? Was the user missing? Was the user already inactive? The `bool` flattens all failure modes into a single "no." `Result` distinguishes *why* it failed, which determines *how* the caller should react.

It also lacks strict compiler enforcement: the signature doesn't guarantee `user` is non-null on the `true` path. `[NotNullWhen(true)]` helps, but it generates warnings rather than errors.


#### The Result Monad
We want the best of both worlds: the **linear readability** of exceptions, but with the **explicit safety** of return values.

```csharp
// The goal: a linear pipeline that short-circuits on failure.
// (Helper methods ParseId/FindUser/Deactivate are shown below.)
public Result<User, Error> DeactivateUser(string inputId) =>
    ParseId(inputId)
        .Bind(FindUser)
        .Bind(Deactivate);
```
We'll build this step-by-step.

### Introducing Result<TSuccess, TError>

> *Note on Naming:* In functional programming, this operation is called `flatMap` (or `SelectMany` in LINQ). We use the name **`Bind`** here to keep it distinct from `Map` and to match the convention established in Part 1.

```csharp
// A simple, structured error type (avoiding "primitive obsession" with strings)
public record Error(string Code, string Message);

// Educational implementation of Result<TSuccess, TError>.
//
// Performance Note: In a high-throughput production library, this should be a `readonly struct` 
// to avoid heap allocations. We use a `class` here for simplicity in demonstration.
//
// Correctness Note: This intentionally omits defensive null/default-state checks to keep the example focused.
// Don’t copy this into production; use a well-tested library implementation.
public sealed class Result<TSuccess, TError>
{
    private readonly TSuccess _value;
    private readonly TError _error;

    // Private constructors ensure valid state
    private Result(TSuccess value)
    {
        IsSuccess = true;
        _value = value;
        _error = default;
    }

    private Result(TError error)
    {
        IsSuccess = false;
        _value = default;
        _error = error;
    }

    // The "Unit" operation (lifts a value into the Monad).
    // We name it 'Ok' to follow standard C# conventions (similar to 'Some' in Part 1).
    public static Result<TSuccess, TError> Ok(TSuccess value) => new Result<TSuccess, TError>(value);
    public static Result<TSuccess, TError> Fail(TError error) => new Result<TSuccess, TError>(error);

    // ------------------------------------------------------------
    // Queries (For domain logic, prefer Match over checking these)
    // ------------------------------------------------------------
    public bool IsSuccess { get; }
    public bool IsFailure => !IsSuccess;

    // Map: Transform the success value (TSuccess -> U)
    public Result<U, TError> Map<U>(Func<TSuccess, U> f)
    {
        if (IsSuccess)
        {
            // Explicitly call the factory. Clear to Java/Rust/JS devs.
            return Result<U, TError>.Ok(f(_value));
        }

        // Propagate the existing error
        return Result<U, TError>.Fail(_error);
    }

    // Bind: Chain operation (TSuccess -> Result<U, TError>)
    public Result<U, TError> Bind<U>(Func<TSuccess, Result<U, TError>> f)
    {
        if (IsSuccess)
        {
            return f(_value);
        }

        return Result<U, TError>.Fail(_error);
    }

    // Match: The only way to extract the value
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

> **Side Note: LINQ Integration**
> If you rename `Bind` to **`SelectMany`** (and add the appropriate overloads), C# allows you to use LINQ query syntax:

```csharp
var result = 
    from id in ParseId(input)
    from user in FindUser(id)
    select user;
```

> We are sticking to explicit method chaining (`Bind`) in this post to make the data flow visible, but production libraries usually support both.

> Production note: implement equality (`Equals`, `GetHashCode`, etc.) and consider default-value behavior; omitted for brevity.
>
> **Exception policy:** `Bind` does not catch exceptions thrown inside `f(...)`. Treat bugs and true system failures as exceptions; use `Result` for expected domain/validation outcomes.

### Using `Result` (Map/Bind/Match)


***

```csharp
Result<int, Error> failure = Result<int, Error>.Fail(new Error("404", "Not found"));
Result<int, Error> doubled = Result<int, Error>.Ok(42).Map(x => x * 2);
var doubledValue = doubled.Match(ok: v => v, err: _ => -1);
// doubledValue == 84

Result<string, Error> GetUserId(string token) =>
    string.IsNullOrWhiteSpace(token)
        ? Result<string, Error>.Fail(new Error("Auth", "Empty token"))
        : Result<string, Error>.Ok("user-123");
// GetUserId("tok") => Ok("user-123")
// GetUserId("")    => Fail(Error("Auth", "Empty token"))

// Gotcha: if the function already returns Result<...>, Map will *nest* the Result:
Result<Result<string, Error>, Error> nestedUserId =
    Result<string, Error>.Ok("tok_abc123").Map(GetUserId);

// Solution: use Bind/FlatMap to keep it flat:
Result<string, Error> flatUserId =
    Result<string, Error>.Ok("tok_abc123").Bind(GetUserId);

Result<int, Error> GetOrderCount(string userId) =>
    userId.StartsWith("user-")
        ? Result<int, Error>.Ok(7)
        : Result<int, Error>.Fail(new Error("Db", "Invalid user id"));
// GetOrderCount("user-123") => Ok(7)
// GetOrderCount("nope")     => Fail(Error("Db", "Invalid user id"))

Result<int, Error> count = 
    Result<string, Error>.Ok("tok_abc123")
        .Bind(GetUserId)
        .Bind(GetOrderCount); 
// Returns Ok(7). If any step failed, it would return that error.
var countValue = count.Match(ok: v => v, err: _ => -1);
// countValue == 7

Result<int, Error> count2 =
    Result<string, Error>.Ok("") // empty token
        .Bind(GetUserId)
        .Bind(GetOrderCount);
var count2Code = count2.Match(ok: _ => "ok", err: e => e.Code); // "Auth"
```

We get a few nice things:

- **Control flow once**: no `if` ladders and repeated manual checks/returns; you just keep `Map`/`Bind`-ing.
- **Clear signatures**: `Result<TSuccess, TError>` encodes failure in the type, so callers can handle it explicitly.
- **Composable pipelines**: `Bind` chains dependent steps without nesting.
- **Boundary handling**: at the edge, you typically unwrap via `Match` (shown next).

Aside: What's a "boundary"? It's where you stop composing and turn a `Result<...>` into actions (HTTP responses, UI updates, logs) using `Match`.

In C#, you're often wrapping APIs that weren't designed for this style, so some glue code is unavoidable.

> **Critical Design Note: Validation vs. Flow**
> 
> You might notice that our `Bind` function "fails fast", it stops on the *first* error. This is perfect for the pipeline above (you can't query the DB if the ID is invalid).
>
> However, this short-circuiting behavior is ill-suited for input validation. In scenarios like registration forms, users expect to see *all* errors (Email is invalid AND Password is weak), not just the first one.
>
> *   **Use Result (Monad)** for sequential logic where step B depends on step A.
> *   **Use Validation (Accumulator)** for independent checks (like form fields).
>

### Unwrapping with `Match` (at the boundary)
Once you have a `Result<TSuccess, TError>`, you eventually need to turn it into a single value or action. `Match` is the "exit" function: you provide two handlers, and it runs exactly one of them.

```csharp
Result<int, Error> result = Result<int, Error>.Ok(1);
var message = result.Match(
    ok:  v => $"Ok({v})",
    err: e => $"Fail({e.Code}: {e.Message})");
```

At some point you need the error value. As with `Maybe`, prefer composing and unwrapping once at the boundary.

**A note on `IsSuccess` / `IsFailure`**

> "We expose `IsSuccess` and `IsFailure` for convenient integration with standard C# features like LINQ queries (`results.Where(r => r.IsFailure)`) and UI binding.
>
> However, notice we do **not** expose the internal value directly. To act on the data, you must use `Match`. This prevents the common mistake of checking the flag but forgetting to handle the error case."

In other words: sometimes you need to ask a **Boolean question** (“Did it work?”) to interop with the rest of C# (simple `if` checks, LINQ filtering, UI binding). But when you want to *do something with the value*, prefer `Match` so the error path stays explicit and handled.

For example, filtering failures is pleasant with a query property:

```csharp
var failures = results.Count(r => r.IsFailure);
```

**Why no `.Value` property?**

This tutorial `Result` doesn’t expose a `public Value` property. That’s intentional: it nudges you toward `Match` instead of manual inspection.

```csharp
// ⚠️ ANTI-PATTERN (hypothetical — not implemented in this tutorial)
// If Result exposed a public Value property, it would be tempting to do this:
//
// if (result.IsSuccess)
// {
//     // Depending on the implementation, this might throw or be null if you get it wrong.
//     var val = result.Value;
// }
```

By keeping the state private and forcing you to use `Match`, the compiler ensures you *always* handle the error case. You cannot access the success value without providing a plan for the error.

Also avoid adding helper methods like `ValueOrThrow()`. They encourage you to ignore the error case, which defeats the purpose of the `Result` type.

With `Result<TSuccess, TError>`, the error is part of the type, so you’ll usually surface it at the edge (UI, logs, HTTP response, etc.) via `Match`.

### Putting it together: the Deactivate User pipeline
Now that we have `Result` and `Error`, we can write the domain pipeline as a few small steps. Notice that persistence happens at the boundary, after `Match`:

```csharp
public sealed class User
{
    public int Id { get; init; }
    public bool IsActive { get; set; } = true;
}

public interface IUserRepo
{
    User? Find(int id);
    void Save(User user);
}

public sealed class UserService
{
    private readonly IUserRepo _repo;
    public UserService(IUserRepo repo) => _repo = repo;

    // The Pipeline: Orchestrates validation and data retrieval
    public Result<User, Error> DeactivateUser(string inputId) =>
        ParseId(inputId)
            .Bind(FindUser)
            .Bind(Deactivate);

    // Boundary: exit Result and perform effects (persistence, logging, etc.)
    public string DeactivateUserAndSave(string inputId) =>
        DeactivateUser(inputId).Match(
            ok: user =>
            {
                _repo.Save(user);
                return "User deactivated";
            },
            err: e => $"Deactivate failed: {e.Code} - {e.Message}");

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

        // Functionally, we should return a new object (e.g., `user with { IsActive = false }`).
        // Pragmatically, we mutate the existing EF Core entity to simplify persistence.
        user.IsActive = false;
        return Result<User, Error>.Ok(user);
    }
}
```

> **A Note on I/O and Side Effects**
> You'll notice this pipeline mixes Reads (`FindUser`) with Logic (`Deactivate`).
> In Pragmatic C# (Railway Oriented Programming), this is common: we use `Result` to orchestrate the "Decision" phase, which often requires fetching data (and `NotFound` is usually the #1 use case).
> However, notice that the Write (`_repo.Save`) happens outside the pipeline, in the `Match` block.
> This follows the "Functional Core, Imperative Shell" principle (roughly):
> Pipeline: Gather data and make a decision (returns `Result`).
> Boundary: If successful, commit the side effect (`Save`).

> **Functional Purity Note:**
> In strict Functional Programming, data is immutable. Instead of setting `user.IsActive = false`, we would return a new copy of the user (e.g., using C# records and `with` expressions).
> However, most C# applications use ORMs (like Entity Framework) that track changes on mutable objects. To keep this tutorial focused on Error Handling rather than State Management, we stick to the idiomatic C# approach of mutating the entity.

In a real app, that “boundary” method usually lives in an application service with a transaction; it’s shown inline here for brevity.

### The Async Reality (Async composition friction)

In modern C#, almost all I/O (Database, HTTP) is asynchronous and returns `Task<T>`. This creates a major friction point.

In a real application, `FindUser` would likely be a database call returning `Task<User?>`. This would require `BindAsync` (or similar async bridges) to keep the pipeline linear without reintroducing nesting.

**The Problem:**
`Task<Result<...>>` is a type wrapped in a type. Standard `Bind` expects a `T`, but your previous step returns a `Task`. You cannot access the `Result` inside without `await`-ing it first. This forces you to break the chain, await the result, unwrap it, and manually start the next step—recreating the nesting we tried to avoid.

```csharp
// The Problem: Without Async support, we are back to nesting
var emailResult =
    await (await GetTokenAsync()) // Task<Result<string, Error>>
        .Match(
            ok: async token =>
            {
                var userResult = await GetUserAsync(token); // Task<Result<User, Error>>

                return await userResult.Match(
                    ok:  user => SendEmailAsync(user), // Task<Result<bool, Error>>
                    err: e => Task.FromResult(Result<bool, Error>.Fail(e)));
            },
            err: e => Task.FromResult(Result<bool, Error>.Fail(e)));
```

To fix this, you need "Async Bridges" (e.g., `BindAsync` or `SelectManyAsync`).

**The Friction:** Without these extension methods, this pattern in C# is painful. You end up manually `await`-ing every step, which ruins the declarative flow. While we aren't building those extensions in this tutorial, essentially every production library (LanguageExt, FluentResults, CSharpFunctionalExtensions) provides them out of the box.

### A Warning on Implementation
Maintenance Note:
Async combinators need careful handling of cancellation, context capture, and exceptions.

Writing your own `Result` type is great for learning, but maintaining async extensions is a burden. For production, consider adopting a dedicated library.

When you graduate from this tutorial to a real app, use:
- ErrorOr (Simple, struct-based)
- FluentResults (Rich features)
- LanguageExt (Strict functional style)

These libraries allow you to write the code we want to write:

```csharp
// What these libraries allow you to do:
public Task<Result<User, Error>> DeactivateUser(string inputId) =>
    ParseIdAsync(inputId)          // Task<Result<int, Error>>
        .BindAsync(FindUserAsync)  // Task<Result<User, Error>>
        .BindAsync(DeactivateAsync);
```

With `Result<TSuccess, TError>`, since an error type is explicitly specified, you’ll usually want to surface it at the edge (UI, logs, HTTP response, etc.). That’s what `Match` is for.

### Exiting the Monad (The API Boundary)

`Result<TSuccess, TError>` is an internal domain type. At the edges of your system (API `Controllers`, UI Views, etc.) collapse it into a boundary type (e.g., `IActionResult`) using `Match`.

**Never return** a raw `Result` object directly to the frontend. It’s an internal plumbing tool, not a public data contract. Returning it is a **leaky abstraction**: it forces your JavaScript client to learn about your internal C# architecture.

In ASP.NET Core, **`ProblemDetails` is the standard JSON shape for errors**. That’s why mapping `Result` → `ProblemDetails` is usually better than inventing a custom `{ success: false, error: ... }` wrapper: you keep HTTP semantics (status codes), stay idiomatic for .NET clients/middleware, and still surface structured error codes/messages.

**The "Russian Doll" risk**

If you return a `Result<...>` directly from a controller, you leak your internal abstraction to the frontend and create awkward wrapper JSON (often something like `{ "isSuccess": true, "value": ... }`).

Exposing an internal `isSuccess` wrapper couples clients to server implementation details. Prefer HTTP status codes and return the resource (or a standard error like `ProblemDetails`) directly.

```json
{
  "isSuccess": true,
  "value": { "id": 123, "name": "Ada", "isActive": true }
}
```

```json
{
  "isSuccess": false,
  "error": { "code": "NotFound", "message": "User 123 not found" }
}
```

**The fix: unwrap at the boundary**
Treat `Result` as internal plumbing: use `Match` at the boundary to map it into standard HTTP responses.

```csharp
// Treat Result as internal: unwrap it at the boundary into a standard response.

[HttpGet("{id}")]
public async Task<IActionResult> GetUser(string id)
{
    Result<User, Error> result = await _userService.Get(id);

    // Use Match to unwrap the Result back into the "Real World"
    return result.Match<IActionResult>(
        ok: user => Ok(user),
        err: error => error.Code switch
        {
            "NotFound" => NotFound(new ProblemDetails { Title = error.Code, Detail = error.Message, Status = 404 }),
            "Parse" or "Validation" => BadRequest(new ProblemDetails { Title = error.Code, Detail = error.Message, Status = 400 }),
            // Avoid leaking internal details. For true "unexpected" failures, prefer centralized exception handling.
            _ => StatusCode(500, new ProblemDetails { Title = "Unexpected", Detail = "An unexpected error occurred.", Status = 500 })
        }
    );
}
```

```json
{ "id": 123, "name": "Ada", "isActive": true }
```

```json
{ "title": "NotFound", "detail": "User 123 not found", "status": 404 }
```

### Testing Strategies

Since we are no longer throwing exceptions, `[ExpectedException]` attributes don't apply. Instead, you assert on the state of the `Result`.

```csharp
[Fact]
public void DeactivateUser_ReturnsFailure_WhenUserNotFound()
{
    // Arrange
    var repo = new InMemoryUserRepo(); // empty repo => not found
    var service = new UserService(repo);

    // Act
    var result = service.DeactivateUser("123");

    // Assert
    Assert.True(result.IsFailure);
    
    // We inspect the error using Match to ensure it's the *correct* failure
    var errorCode = result.Match(
        ok => "UNEXPECTED_SUCCESS", 
        err => err.Code
    );
    Assert.Equal("NotFound", errorCode);
}
```

### Takeaways

1.  **One shape for error flow:** Use `Result<TSuccess, TError>` to keep sequential workflows linear via `Map`/`Bind` instead of nesting `if`s.
2.  **Fail-fast is the point:** `Bind` stops on the first failure. That's ideal for dependent pipelines (and not ideal for "collect all errors" validation).
3.  **Unwrap at the boundary:** Don't serialize `Result` to JSON or return `isSuccess` flags. Use `Match` at the edge to turn it into HTTP/UI responses.
4.  **Prefer established libraries:** For production, rely on maintained packages for async composition (`Task<Result<...>>`) and edge-case handling.

> **Further Reading (The "Railway" Metaphor):**
> This pattern is widely known in the .NET community as **"Railway Oriented Programming,"** a term coined by Scott Wlaschin. If you want to see this concept taken to its logical conclusion (including validation aggregation and parallel tracks), his site [F# for Fun and Profit](https://fsharpforfunandprofit.com/rop/) is the definitive resource.

**A Note on Libraries:**
For production C#, prefer a mature library (e.g., **FluentResults**, **ErrorOr**, **LanguageExt**) rather than maintaining your own.

**Next in the series**: [Monads in C# (Part 3): The Reader Monad](https://alexyorke.github.io/2025/12/20/monads-in-c-sharp-part-3-the-reader-monad/)

[^id]: In real systems, an identifier is often better modeled as a domain type (e.g., `UserId`) rather than a bare number. This post uses `string` at the boundary and parses to `int` to keep the example focused on `Result` composition.