---

title: "Monads in C# (Part 2): Result"
date: 2025-09-13
description: "Build a right-biased Result type in C# and use Map/Bind/Match to compose workflows with explicit failures, including async friction and API boundary handling."
---

**Previously in the series**: [List is a monad (part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/)

> _Note_: This post was substantially rewritten on 2025-12-21.

In Part 1 you built `Maybe` and used `Bind` (aka `FlatMap`) to chain optional steps. This part keeps that shape but lets the "no value" branch carry a reason via `Result<TSuccess, TError>`.

If you think in `LINQ`: `Map` ≈ `Select`, `Bind`/`FlatMap` ≈ `SelectMany`. We’ll stick to method style here to keep focus on the flow rather than syntax.

**What you’ll build:**

1.  Introduce `Result<TSuccess, TError>`.
2.  Apply it to a linear workflow (Deactivate User).
3.  Discuss the async composition friction (`Task<Result<...>>`) and the library hand-off.
4.  Handle the API boundary correctly (avoiding serialization pitfalls).

> Terminology note (Either vs. Result):
> Result<TSuccess, TError> is a convention: it encodes “success vs. failure.”
> You’ll also see Either<L, R>, which encodes “one of two possibilities.” In some libraries, Either is right-biased, so Map/Bind compose the Right value and short-circuit on Left.
> If you use Either<TError, TSuccess>, it’s effectively the same workflow shape as Result<TSuccess, TError>.
> This post uses Result because the names “Success/Error” make the intended meaning hard to misread.

### Result: when “missing” needs a reason

`Maybe<T>` tells us whether a value exists. Sometimes, we need *why* it doesn’t exist. We keep the same straight‑line composition:

*   **Map**: transform the success value.
*   **Bind**: chain a function returning another `Result<...>`.

   ...and add a **failure** branch that carries an error.

Think of it like:
*   `Ok(value)` -> like `Some(value)`
*   `Fail(error)` -> like `None()`, but with a reason

### Scenario: The "Deactivate User" Pipeline

We need to implement a workflow to deactivate a user given a raw `id` **string** from outside the system (e.g., an HTTP query parameter). That string represents the **user’s identifier**, but it isn’t trusted yet — we first parse it into our internal ID representation (an `int` in this post).[^id]

The steps depend on each other:

1.  **Parse:** Parse the raw `string` into an `int`. (If this fails, we cannot proceed).
2.  **Find:** The user must exist in the database. (If missing, we cannot deactivate).
3.  **Business rule:** The user must currently be active. (If already inactive, it's a domain error).

> **Concept Check: Result vs. `T?` (optional)**
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

- **Bugs / invariant violations**: null refs, out-of-range, “this can’t happen” states. Those should throw/crash so you fix the bug.
- **Truly unrecoverable failures**: missing critical startup config, broken invariants, “the database is down”, and similar “we can’t continue” conditions. Failing fast (via a global exception handler/middleware) is usually safer than returning a value the caller can’t do anything with.
- **Validation that must accumulate errors**: if you want “email invalid **and** password weak” in one response, `Result`’s fail-fast monadic chaining is the wrong tool; prefer a validation/accumulator type.
- **Shotgun validation in the domain**: if every domain method accepts weak primitives (`string email`) and returns `Result` for basic format checks, you’re not modeling invariants—parse once at the boundary into strong types/value objects, then keep the core domain free of “is this string valid?” checks.
- **Side-effect-only chains** (`Result<Unit>` / `Result<void>`): chaining logging/metrics/email/cache writes via `Bind` often creates artificial sequencing and hides partial-success realities. Prefer doing effects at the boundary (or explicit orchestration patterns like jobs/sagas) rather than monadifying every void step.
- **Partial success / batch work**: if “process 100 items” can succeed for 95 and fail for 5, a single `Result<List<T>, E>` forces the wrong all-or-nothing semantics. Prefer a dedicated batch result type (successes + failures) or a list of per-item results.
- **Hot paths where allocations matter**: in managed runtimes, wrapping everything in `Result` can create allocation/GC pressure on the success path. If failure is extremely rare and throughput is paramount, exceptions (or other low-level patterns) can be a better trade.
- **Effect stacking / “transformer hell”**: if you end up drowning in `Task<Result<...>>` glue (and you’re not using a library that smooths it), the complexity may outweigh the benefits.

### Comparison patterns (exceptions vs tuples vs Try/out vs Result)

#### Example 1: Baseline Exceptions
In a common C# style, failures are often signaled with exceptions. That means control flow is implicit: any line might abort the method by throwing.

```csharp
public void DeactivateUser(string inputId)
{
    // 1. Parse (May throw FormatException)
    int id = int.Parse(inputId);

    // 2. Find (May throw NullReference or Custom Exception)
    User user = _repo.Find(id); 
    if (user == null) throw new KeyNotFoundException($"User {id} not found");

    // 3. Logic (May throw InvalidOperationException)
    if (!user.IsActive) throw new InvalidOperationException("User is already inactive");

    user.IsActive = false;
    _repo.Save(user);
}
```

**Critique:** This works, and for true system failures (DB down, OutOfMemory), exceptions are the right tool. But "User Not Found" or "User Inactive" are expected domain outcomes. Using exceptions here makes `void DeactivateUser(string)` hide expected outcomes and pushes callers into `try`/`catch` control flow.

#### Example 2: The Tuple Pattern
To make failures explicit, we might return a tuple `(Success, Error)`.

```csharp
public (bool Success, string Error) DeactivateUser(string inputId)
{
    if (!int.TryParse(inputId, out int id)) 
        return (false, "Invalid ID format");

    User? user = _repo.Find(id);
    if (user == null) 
        return (false, "User not found");

    if (!user.IsActive) 
        return (false, "User is already inactive");

    user.IsActive = false;
    _repo.Save(user);
    return (true, "");
}
```

**Critique:** This is "honest," but it creates **Manual Error Propagation**. You have to explicitly check the `Success` boolean after *every single step*. If you forget one check, the execution continues with invalid data (or nulls). Half your code becomes `if (!success) return ...`, obscuring the actual business logic.

#### Example 3: The Try/out Pattern
Another approach is the Try pattern: return a bool for success and write the result to an `out` parameter. Assume the repository exposes `TryFind` as well.

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

This is performant and idiomatic for low-level logic, and it composes nicely via short-circuiting. The trade-off is that it **swallows the reason**: `false` doesn’t tell us whether it failed because input was invalid, the user wasn’t found, or the user was inactive (unless you add another `out` for an error). `Result` adds the “why”.

It also lacks strict compiler enforcement: the signature doesn't guarantee `user` is non-null on the `true` path. `[NotNullWhen(true)]` helps, but it generates warnings rather than errors.


#### Example 4: The Result Monad
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

One important caveat: `Result` isn’t “free.” In this toy implementation you pay overhead on the success path (allocations and delegate calls). Exceptions are the inverse: cheap on success, expensive on failure. `Result` shines when failures are **expected domain outcomes** and you want explicit, composable handling.

Also: if you only have one small workflow, guard clauses are perfectly fine. `Result` becomes more valuable when you can **reuse steps** and keep error handling consistent across many call sites.

### Introducing Result<TSuccess, TError>

```csharp
// A simple, structured error type (avoiding "primitive obsession" with strings)
public record Error(string Code, string Message);

// Educational implementation of Result<TSuccess, TError>.
// Production note: in a production library, this would often be a `readonly struct` to reduce memory allocations.
// We use a `class` here to keep the implementation code simple.
//
// Note: this uses `!` (null-forgiveness) to keep the code short; production libraries enforce invariants more strictly.
public sealed class Result<TSuccess, TError>
{
    private readonly TSuccess? _value;
    private readonly TError? _error;
    private readonly bool _isSuccess;

    private Result(TSuccess value)
    {
        _isSuccess = true;
        _value = value;
        _error = default;
    }

    private Result(TError error)
    {
        _isSuccess = false;
        _value = default;
        _error = error;
    }

    public static Result<TSuccess, TError> Ok(TSuccess value) => new(value);
    public static Result<TSuccess, TError> Fail(TError error) => new(error);

    public bool IsSuccess => _isSuccess;
    public bool IsFailure => !_isSuccess;

    // Map: Transform value (TSuccess -> U)
    public Result<U, TError> Map<U>(Func<TSuccess, U> f)
    {
        return _isSuccess
            ? Result<U, TError>.Ok(f(_value!))
            : Result<U, TError>.Fail(_error!);
    }

    // Bind: Chain operation (TSuccess -> Result<U, TError>)
    public Result<U, TError> Bind<U>(Func<TSuccess, Result<U, TError>> f)
    {
        return _isSuccess
            ? f(_value!)
            : Result<U, TError>.Fail(_error!);
    }

    // Match: The only way to extract the value
    public TResult Match<TResult>(Func<TSuccess, TResult> ok, Func<TError, TResult> err)
    {
        return _isSuccess ? ok(_value!) : err(_error!);
    }
}
```

> Production note: implement equality (`Equals`, `GetHashCode`, etc.) and consider default-value behavior; omitted for brevity.
>
> **Exception policy:** `Bind` does not catch exceptions thrown inside `f(...)`. That’s intentional. `Result` is for *expected* domain/validation outcomes; unhandled exceptions are still the right mechanism for bugs and true system failures (null refs, invariants violated, OOM, DB driver blowing up, etc.).

### Using `Result` (core operations)

**Key idea:** Bind short‑circuits: once you hit a failure, the error flows through unchanged and downstream steps don’t run. The Result monad itself is responsible for running or not running the next steps.


***

```csharp
Result<int, Error> failure = Result<int, Error>.Fail(new Error("404", "Not found"));
Result<int, Error> doubled = Result<int, Error>.Ok(42).Map(x => x * 2);
var doubledValue = doubled.Match(ok: v => v, err: _ => -1);

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

What `Match` guarantees:

- You handle both cases (`Ok` and `Fail`) in one place.
- The handlers only see the value they're allowed to see (`TSuccess` vs `TError`).

At some point you need the error value. As with `Maybe`, prefer composing and unwrapping once at the boundary.

**Why no `.Value` property?**

You might notice the `Result` class above doesn't expose a `public Value` property. This is intentional. If we exposed it, it would be tempting to write:

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

    // Domain pipeline: no I/O
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

> **Functional Purity Note:**
> In strict Functional Programming, data is immutable. Instead of setting `user.IsActive = false`, we would return a new copy of the user (e.g., using C# records and `with` expressions).
> However, most C# applications use ORMs (like Entity Framework) that track changes on mutable objects. To keep this tutorial focused on Error Handling rather than State Management, we stick to the idiomatic C# approach of mutating the entity.

In a real app, that “boundary” method usually lives in an application service with a transaction; it’s shown inline here for brevity.

### The Async Reality (Async composition friction)

In modern C#, almost all I/O (Database, HTTP) is asynchronous and returns `Task<T>`. This creates a major friction point.

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

To fix this, you need "Async Bridges" - extension methods like `BindAsync` that handle the `await` for you inside the chain.

> Note: We are **not** implementing `BindAsync`/`MapAsync` in this tutorial. Doing it well quickly turns into boilerplate around `Task` awaiting, cancellation, context, and exception behavior. The goal here is to understand the *shape* of composition; in production, use a library that provides these async operators out of the box.

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

### Nesting: Maybe inside Result
Monads are composable. Sometimes you need to wrap a `Maybe<T>` inside a `Result<TSuccess, TError>`. This creates the type `Result<Maybe<T>, Error>`.

The most common use case is **optional fields** (e.g., a "Phone Number" on a profile):

- If the user sends a valid phone number, we update it (**Ok + Some**).
- If the user sends nothing, that's valid, but we do nothing (**Ok + None**).
- If the user sends `"123-garbage"`, that is an error (**Fail**).

Here is how you build and consume that structure without complex extension methods:

```csharp
public record Phone(string Value);

// Scenario: Parsing an optional input field
public Result<Maybe<Phone>, Error> ValidateOptionalPhone(string? input)
{
    // Case 1: Input is missing (null or empty)
    // This is NOT a failure. It's a valid "Empty" state.
    if (string.IsNullOrWhiteSpace(input))
    {
        return Result<Maybe<Phone>, Error>.Ok(Maybe<Phone>.None());
    }

    // Case 2: Input exists, but is invalid
    // This IS a failure.
    if (!input.Contains("-"))
    {
        return Result<Maybe<Phone>, Error>.Fail(new Error("Format", "Phone must contain dashes"));
    }

    // Case 3: Input exists and is valid
    // This is Success containing Data.
    var phone = new Phone(input);
    return Result<Maybe<Phone>, Error>.Ok(Maybe<Phone>.Some(phone));
}
```

### Exiting the Monad (The API Boundary)

`Result<TSuccess, TError>` is an internal domain type. At the edges of your system (API `Controllers`, UI Views, etc.) collapse it into a boundary type (e.g., `IActionResult`) using `Match`.

Never return a raw `Result` object directly to the frontend. It’s an internal plumbing tool, not a public data contract. Returning it is a **leaky abstraction**: it forces your JavaScript client to learn about your internal C# architecture.

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

### Why does this feel so complicated?

Does this feel like more work than `try`/`catch`? The trade-off is that complexity is visible in method signatures rather than hidden in the call stack: implicit control flow becomes explicit data flow.

### Testing Strategies

Since we are no longer throwing exceptions, `[ExpectedException]` attributes don't apply. Instead, you assert on the state of the `Result`.

```csharp
[Fact]
public void DeactivateUser_ReturnsFailure_WhenUserNotFound()
{
    // Arrange
    var repo = new InMemoryUserRepo(); // empty repo => not found

    // Act
    var result = DeactivateUser("123");

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

**A Note on Libraries:**
For production C#, prefer a mature library (e.g., **FluentResults**, **ErrorOr**, **LanguageExt**) rather than maintaining your own. Disclaimer: I have not used these libraries extensively.

**Next in the series**: [Monads in C# (Part 3): The Reader Monad](https://alexyorke.github.io/2025/12/20/monads-in-c-sharp-part-3-the-reader-monad/)

[^id]: In real systems, an identifier is often better modeled as a domain type (e.g., `UserId`) rather than a bare number. This post uses `string` at the boundary and parses to `int` to keep the example focused on `Result` composition.