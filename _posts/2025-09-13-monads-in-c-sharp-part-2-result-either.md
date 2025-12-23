---

title: "Monads in C# (Part 2): Result (Either)"
date: 2025-09-13
---

**Previously in the series**: [List is a monad (part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/)

> _Note_: This post was substantially rewritten on 2025-12-21.

In Part 1 you built `Maybe` and used `Bind` (aka `FlatMap`) to chain optional steps. This part keeps that shape but lets the "no value" branch carry a reason via `Result<TSuccess, TError>`.

If you think in `LINQ`: `Map` ≈ `Select`, `Bind`/`FlatMap` ≈ `SelectMany`. We’ll stick to method style here to keep focus on the flow rather than syntax.

**What you’ll build:**

1.  Introduce `Result<TSuccess, TError>` (aka Either).
2.  Apply it to a linear workflow (Deactivate User).
3.  Discuss the async composition friction (`Task<Result<...>>`) and the library hand-off.
4.  Handle the API boundary correctly (avoiding serialization pitfalls).

> **Language note:** FP libraries often call this **Either**. Conventions vary (often `Either<L, R>` with Left = error), so I use `Result<TSuccess, TError>` to avoid left/right ambiguity.
>
> **Bias note:** This is the common **right‑biased** Either/Result: it’s a monad over `TSuccess` (the error type stays fixed through `Bind`).

### Result (aka Either): when “missing” needs a reason

`Maybe<T>` tells us whether a value exists. Sometimes, we need *why* it doesn’t exist. We keep the same straight‑line composition:

*   **Map**: transform the success value.
*   **Bind**: chain a function returning another `Result<...>`.

   ...and add a **failure** branch that carries an error.

Think of it like:
*   `Ok(value)` -> like `Some(value)`
*   `Fail(error)` -> like `None()`, but with a reason

### Scenario: The "Deactivate User" Pipeline

We need to implement a workflow to deactivate a user based on a raw string ID (e.g., from an HTTP query parameter). This process has strict dependencies:

1.  **Parse:** The string must be a valid integer.[^id] (If this fails, we cannot proceed).
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

These steps are **sequential**. Step 2 cannot run if Step 1 fails. `Result` models this fail-fast workflow; first, let's look at how we typically solve it.

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

**Critique:** This is "honest," but it creates the "Pyramid of Doom" (lots of explicit `if` checks). It also allows nonsensical states, e.g., `(true, "some error")`.

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

This composes nicely via short-circuiting, but it doesn't provide a structured failure reason (unless you add another `out` for an error).

It also lacks strict compiler enforcement: the signature doesn't guarantee `user` is non-null on the `true` path. `[NotNullWhen(true)]` helps, but it generates warnings rather than errors.


#### Example 4: The Result Monad
We want the best of both worlds: the **linear readability** of exceptions, but with the **explicit safety** of return values.

```csharp
// The goal: a linear pipeline that short-circuits on failure.
// (Helper methods ParseId/FindUser/Deactivate/Save are shown below.)
public Result<User, Error> DeactivateUser(string inputId) =>
    ParseId(inputId)
        .Bind(FindUser)
        .Bind(Deactivate)
        .Bind(Save);
```
We'll build this step-by-step.

### Introducing Result<TSuccess, TError>

```csharp
// A simple, structured error type (avoiding "primitive obsession" with strings)
public record Error(string Code, string Message);

// Educational implementation of Result<TSuccess, TError>.
// Production notes: prefer `readonly struct` for performance; avoid string errors (use a structured `Error`).
public sealed class Result<TSuccess, TError>
{
    // Track which branch we're on (mirrors Maybe's internal "has value" flag).
    private readonly bool _isOk;

    // Success value (when _isOk is true).
    private readonly TSuccess _value;

    // Error value (when _isOk is false).
    private readonly TError _error;

    public bool IsSuccess => _isOk;
    public bool IsFailure => !_isOk;

    // Escape hatches (some libraries expose these). Prefer `Map`/`Bind` for composition,
    // and `Match` once at the boundary.
    public TSuccess? Value => _isOk ? _value : default;
    public TError? Error => _isOk ? default : _error;

    // Success constructor (parallel to Maybe.Some).
    private Result(TSuccess value)
    {
        _isOk = true;
        _value = value;
        _error = default!;
    }

    // Error constructor (parallel to Maybe.None but with a reason).
    private Result(TError error)
    {
        _isOk = false;
        _value = default!;
        _error = error;
    }

    // Factory methods (shape: static constructors like Maybe.Some/None).
    public static Result<TSuccess, TError> Ok(TSuccess value) => new(value);
    public static Result<TSuccess, TError> Fail(TError error) => new(error);

    // Note: No implicit conversions. Call `Ok(...)` / `Fail(...)` explicitly.

    // Map: Transform value (TSuccess -> U), keep error (TError)
    public Result<U, TError> Map<U>(Func<TSuccess, U> f)
    {
        return _isOk
            ? Result<U, TError>.Ok(f(_value))
            : Result<U, TError>.Fail(_error);
    }

    // Bind: Chain operation (TSuccess -> Result<U, TError>)
    public Result<U, TError> Bind<U>(Func<TSuccess, Result<U, TError>> f)
    {
        return _isOk
            ? f(_value)
            : Result<U, TError>.Fail(_error);
    }

    // Match: Handle both cases
    public TResult Match<TResult>(Func<TSuccess, TResult> ok, Func<TError, TResult> err)
    {
        return _isOk ? ok(_value) : err(_error);
    }
}
```

> Production note: implement equality (`Equals`, `GetHashCode`, etc.) and consider default-value behavior; omitted for brevity.

### Using `Result` (core operations)

**Key idea:** Bind short‑circuits: once you hit a failure, the error flows through unchanged and downstream steps don’t run. The Result monad itself is responsible for running or not running the next steps.


***

```csharp
Result<int, Error> failure = Result<int, Error>.Fail(new Error("404", "Not found"));
Result<int, Error> doubled = Result<int, Error>.Ok(42).Map(x => x * 2);
// "Run" it:
// doubled.Match(ok: v => v, err: _ => -1) => 84
// doubled.IsSuccess => true

Result<string, Error> GetUserId(string token) =>
    string.IsNullOrWhiteSpace(token)
        ? Result<string, Error>.Fail(new Error("Auth", "Empty token"))
        : Result<string, Error>.Ok("user-123");
// GetUserId("tok") => Ok("user-123")
// GetUserId("")    => Fail(Error("Auth", "Empty token"))

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
// "Run" it:
// count.Match(ok: v => v, err: _ => -1) => 7

Result<int, Error> count2 =
    Result<string, Error>.Ok("") // empty token
        .Bind(GetUserId)
        .Bind(GetOrderCount);
// count2.IsFailure => true
// count2.Match(ok: _ => "ok", err: e => e.Code) => "Auth"
```

We get a few nice things:

- **Control flow once**: no `if` ladders, no early returns, no out-parameter defaults; you just keep `Map`/`Bind`-ing.
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

```csharp
// Anti-Pattern: Manual Inspection
// While properties like .Value and .Error exist as escape hatches,
// using them for control flow bypasses the safety guarantees of the pattern.
Result<string, Error> result = Result<string, Error>.Ok("hello");
if (result.Value != null) {
    Console.WriteLine(result.Value);
} else {
    Console.WriteLine(result.Error);
}
```
Directly inspecting state reintroduces the imperative branching we tried to eliminate. It also makes the code brittle: if `TSuccess` is a nullable type, checking `Value != null` is no longer a valid success test.

With `Result<TSuccess, TError>`, the error is part of the type, so you’ll usually surface it at the edge (UI, logs, HTTP response, etc.) via `Match`.

### Putting it together: the Deactivate User pipeline
Now that we have `Result` and `Error`, we can write the full linear workflow:

```csharp
public sealed class User
{
    public required int Id { get; init; }
    public bool IsActive { get; set; } = true;
}

public interface IUserRepo
{
    User? Find(int id);
    bool TryFind(int id, [System.Diagnostics.CodeAnalysis.NotNullWhen(true)] out User? user);
    void Save(User user);
}

public sealed class DeactivateUserWorkflow
{
    private readonly IUserRepo _repo;

    public DeactivateUserWorkflow(IUserRepo repo) => _repo = repo;

    public Result<User, Error> DeactivateUser(string inputId) =>
        ParseId(inputId)          // Result<int, Error>
            .Bind(FindUser)       // Result<User, Error>
            .Bind(Deactivate)     // Result<User, Error>
            .Bind(Save);          // Result<User, Error>

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

        user.IsActive = false;
        return Result<User, Error>.Ok(user);
    }

    // Side effect as an explicit step.
    // Some libraries call this `Tap`; here we just return the original user back into the chain.
    private Result<User, Error> Save(User user)
    {
        _repo.Save(user);
        return Result<User, Error>.Ok(user);
    }
}
```

At the boundary, you consume that `Result<User, Error>` with `Match`:

```csharp
// Example: boundary consumption (e.g., UI / Controller / message)
string message = DeactivateUser("123").Match(
    ok:  _ => "User deactivated",
    err: e => $"Deactivate failed: {e.Code} - {e.Message}");
```

### The Async Reality (Async composition friction)

In modern C#, almost all I/O (Database, HTTP) is asynchronous and returns `Task<T>`. This creates a major friction point.

Our `Bind` method expects a `T` (the value), but your database call returns a `Task<Result<TSuccess, TError>>`. Since the `Result` is wrapped inside a `Task`, the standard `Bind` combinators are not directly accessible.

Without specific extensions to handle the asynchronous container, the linear flow devolves into the "Pyramid of Doom," forcing manual `await` statements at every step:

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
            _ => StatusCode(500, new ProblemDetails { Title = "Unexpected", Detail = error.Message, Status = 500 })
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

### The "Void" Problem (Unit)

Sometimes a method does work but returns nothing (void), like `Log(string msg)`. In Functional Programming, "void" breaks the chain because there is no value to pass to the next step.

One way to model that is `Unit`, a type that simply means "I did the work, but have no value."

C# native syntax distinguishes between `void` and return values, which breaks generic composition (e.g., you cannot write `Result<void>`). Functional libraries bridge this gap with `Unit`—a concrete type representing "void" that can be passed as a generic argument.

```csharp
public readonly struct Unit { public static readonly Unit Value = new Unit(); }

// Now we can have a Result that contains "nothing" but can still fail
Result<Unit, Error> Log(int id) 
{
    if (id < 0) return Result<Unit, Error>.Fail(new Error("Log", "Invalid Id"));
    
    Console.WriteLine($"Id: {id}");
    
    // Return the "Unit" value to signal success-with-no-data
    return Result<Unit, Error>.Ok(Unit.Value);
}
```

### Testing Strategies

Since we are no longer throwing exceptions, `[ExpectedException]` attributes don't apply. Instead, you assert on the state of the `Result` (often with `async Task` tests).

```csharp
[Fact]
public void DeactivateUser_ReturnsFailure_WhenUserNotFound()
{
    // Arrange
    var repo = new InMemoryUserRepo(); // empty repo => not found
    var workflow = new DeactivateUserWorkflow(repo);

    // Act
    var result = workflow.DeactivateUser("123");

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

[^id]: In real systems, an identifier is often better modeled as a domain type (e.g., `UserId`) rather than a bare number. This post uses `int` to keep the example focused on `Result` composition.