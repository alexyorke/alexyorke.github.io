---
title: "A list is a monad (part 2)"
date: 2025-06-30
---

Wow! Part 1 got a bit more traction than expected. I didn't really expect that, part 2 is still a WIP. However, feel free to provide feedback.

In **Part 1**, we introduced the concept of monads using simple examples like a `MaybeMonad` (to represent optional values) and noted that even a list in C# can be viewed through a monadic lens. We implemented a basic `Unit` (to wrap a raw value into a monadic context) and saw how `Map` can apply a function inside the context. However, our `MaybeMonad` wasn’t *quite* a full-fledged monad yet, and we only dealt with one kind of context (missing values). In this second part, we’ll refine our `MaybeMonad` to be a proper monad, then explore **monads for error handling** (the Either/Result pattern) and **monads for deferred computations** like the Reader monad. By the end, we’ll see how these patterns help write clearer, more robust C# code by separating *what* we want to do from *how* things like errors or asynchrony are handled.

## **Recap: Making Maybe a Proper Monad**

In Part 1, we built a simple `MaybeMonad` class to represent an “optional int”, it either held an `int` value or represented the absence of a value. We had a `Unit` (constructor) to create a `MaybeMonad` from an int, and a `Map` method to apply transformations if a value was present. However, to truly qualify as a monad, we should also implement **flatMap** (often called *Bind* in functional terminology) and ensure the type obeys the monad laws. Let’s make a couple of improvements:

* **Hide Constructors:** Make the constructors private and provide static methods like `Unit` to create instances. This ensures the only way to get a `MaybeMonad` is through our controlled methods.

* **Add FlatMap:** Implement a `FlatMap` (or `Bind`) method that takes a function producing another `MaybeMonad` and chains it. This handles nested monadic results without ending up with `MaybeMonad<MaybeMonad<…>>`.

Below is the refined `MaybeMonad` class. First, we show it without generics (just for `int` values) and then we’ll generalize it to any type `T`:
```csharp
public class MaybeMonad

{

    private int value;

    private bool hasValue;

    private MaybeMonad(int value)

    {

        this.value = value;

        this.hasValue = true;

    }

    private MaybeMonad() 

    {

        this.hasValue = false;

    }

    public static MaybeMonad Unit(int value)

    {

        return new MaybeMonad(value);

    }

    public static MaybeMonad Unit()

    {

        return new MaybeMonad();

    }

    public MaybeMonad Map(Func<int, int> func)

    {

        if (hasValue)

        {

            return new MaybeMonad(func(value));

        }

        else

        {

            return this;  // nothing to map, return self

        }

    }

    public MaybeMonad FlatMap(Func<int, MaybeMonad> func)

    {

        if (hasValue)

        {

            return func(value);

        }

        else

        {

            return this;

        }

    }

    public override string ToString() =>

        hasValue ? $"{value}" : "";

}
```
The `FlatMap` is similar to `Map` except that the function `func` returns another `MaybeMonad` directly. Remember that func is the function that you’re passing in to Map. If `this` monad has a value, we apply `func` to that value (potentially yielding a new `MaybeMonad`), and if `this` is empty, we skip the function and just propagate the empty state.

We can test the **monad laws** in this class. For example, the monad laws are:

(1) *Left Identity* – `Unit(a).FlatMap(f)` should equal `f(a)` for any `a` and function `f`;

(2) *Right Identity* – `m.FlatMap(Unit)` should equal `m` for any monad instance `m`;

and (3) *Associativity* – `m.FlatMap(f).FlatMap(g)` should equal `m.FlatMap(x => f(x).FlatMap(g))` for any `m`, `f`, and `g`.

A quick test confirms our `MaybeMonad` abides by these laws:
```csharp
Func<int, MaybeMonad> f = x => MaybeMonad.Unit(x + 1);

Func<int, MaybeMonad> g = x => MaybeMonad.Unit(x * 2);

int a = 5;

var m = MaybeMonad.Unit(a);

// 1) Left Identity

var left1 = MaybeMonad.Unit(a).FlatMap(f);

var left2 = f(a);

Console.WriteLine($"Left Identity:   {left1} == {left2} → {left1.ToString() == left2.ToString()}");

// 2) Right Identity

var right = m.FlatMap(MaybeMonad.Unit);

Console.WriteLine($"Right Identity:  {m} == {right} → {m.ToString() == right.ToString()}");

// 3) Associativity

var assoc1 = m.FlatMap(f).FlatMap(g);

var assoc2 = m.FlatMap(x => f(x).FlatMap(g));

Console.WriteLine($"Associativity:   {assoc1} == {assoc2} → {assoc1.ToString() == assoc2.ToString()}");
```
This yields output indicating all three laws hold true (each comparison prints `True`). Now our `MaybeMonad` is an honest-to-goodness monad!

That said, our `MaybeMonad` is still a bit limited, it currently only works for `int` values. In reality, a Maybe/Optional monad should be able to hold any type. We can introduce **generics** to make `MaybeMonad<T>` polymorphic in the value type:
```csharp
public class MaybeMonad<T>

{

    private readonly T _value;

    private readonly bool _hasValue;

    private MaybeMonad(T value)

    {

        _value = value;

        _hasValue = true;

    }

    private MaybeMonad()

    {

        _hasValue = false;

    }

    public static MaybeMonad<T> Unit(T value)

    {

        return new MaybeMonad<T>(value);

    }

    public static MaybeMonad<T> Unit()

    {

        return new MaybeMonad<T>();

    }

    /// Transforms the contained value to a new type, if present. The new type could be the same type.

    public MaybeMonad<U> Map<U>(Func<T, U> mapper)

    {

        if (_hasValue)

        {

            return MaybeMonad<U>.Unit(mapper(_value));

        }

        else

        {

            return MaybeMonad<U>.Unit();

        }

    }

    /// Applies a function that returns another monad, flattening the result.

    public MaybeMonad<U> FlatMap<U>(Func<T, MaybeMonad<U>> binder)

    {

        if (_hasValue)

        {

            return binder(_value);

        }

        else

        {

            return MaybeMonad<U>.Unit();

        }

    }

    public override string ToString() => _hasValue ? $"{_value}" : "";

}
```
The `Map` function is defined here to take a `Func<T, U>`, meaning it takes a function that takes in some type T, and could return a type U. Type U could be the same type, or it might be a different type–this adds flexibility. For example, you want to convert an integer to a string, T is int, and U is string.

Using our generic `MaybeMonad<T>` looks like this:
```csharp
// Example usage of MaybeMonad<T>

MaybeMonad<int> someNumber = MaybeMonad<int>.Unit(5);

MaybeMonad<int> doubled = someNumber.Map(x => x * 2);

Console.WriteLine(doubled);    // 10

MaybeMonad<int> noNumber = MaybeMonad<int>.Unit();

MaybeMonad<string> stillNone = noNumber.Map(x => x * 2).Map(x => x + " World!");

Console.WriteLine(stillNone);  // Nothing

// Using with strings

MaybeMonad<string> greeting = MaybeMonad<string>.Unit("Hello");

MaybeMonad<string> excited = greeting.Map(s => s + " World!");

Console.WriteLine(excited);      // Hello World!

MaybeMonad<string> noGreeting = MaybeMonad<string>.Unit();

MaybeMonad<string> stillNoGreet = noGreeting.Map(s => s + " World!");

Console.WriteLine(stillNoGreet); // Nothing
```
The `MaybeMonad` encapsulates the logic of “check for null/missing before doing anything.” We no longer have to pepper our code with `if (value != null)` checks – using `Map` and `FlatMap`, the computation just silently skips ahead if there’s “Nothing” inside. This is a great pattern for optional values. But what about *errors*? Maybe an operation didn’t produce a value *because something went wrong*. The Maybe monad doesn’t tell us **why** it’s empty, it just is. Often, for error handling, we want a monad that can carry *either* a result or an error information. Enter the **Either monad**.

## **TryParse vs Try-Catch: Avoiding Exceptions for Expected Errors**

Before diving into the Either monad, let’s examine the problem it helps solve. In typical imperative C# code, error handling is often done via exceptions: you try something and catch exceptions to handle failures. However, using exceptions for **expected conditions** (like invalid user input) is generally discouraged. Why? Because exceptions are meant for exceptional, unexpected situations (like system failures, bugs, etc.), not for normal program flow. Using them for flow control can lead to messy code and performance issues. C# offers methods like `TryParse` (available on numeric types, DateTime, etc.) to handle parsing failures without exceptions. Instead of throwing an exception on bad input, `TryParse` returns `false` and outputs a result only if the parse succeeded. This pattern aligns with the idea that bad input is *anticipated* and shouldn’t be treated as an anomaly.

To illustrate these points, let’s look at a few examples:

### **Example 1: User Input Validation Loop**

Suppose we want to repeatedly prompt a user for a number until they enter a valid numeric value. Using `double.TryParse` makes this straightforward:
```csharp
double value;

while (true)

{

    Console.Write("Enter a number: ");

    string input = Console.ReadLine();

    if (double.TryParse(input, out value))

    {

        break; // parsed successfully, exit loop

    }

    Console.WriteLine("Invalid input, please enter a number.");

}

Console.WriteLine($"You entered {value}.");
```
Here, the loop continues until `TryParse` returns `true`. No exceptions are involved for the normal “invalid input” case – we treat it as an expected part of the loop logic. The code is clear: *try to parse, if fail, prompt again*. The error handling (prompting again) is right next to the parse attempt, making the flow easy to follow.

Now, consider doing the same with exceptions:
```csharp
double value;

while (true)

{

    Console.Write("Enter a number: ");

    string input = Console.ReadLine();

    try

    {

        value = double.Parse(input);  // will throw if not a number

        break;                        // success, exit loop

    }

    catch (FormatException)

    {

        Console.WriteLine("Invalid input, please enter a number.");

        // loop continues on invalid input

    }

}

Console.WriteLine($"You entered {value}.");
```
Functionally, this accomplishes the same thing, but notice how the structure is different. The primary logic of parsing and using the value is interrupted by the `catch` block handling the common failure case. The “happy path” (valid input) isn’t as straightforward because it’s embedded in the try block. This approach also *feels* clunkier – we’re using exceptions to handle something we anticipate will happen (user might type “hello” instead of “42”), which is not what exceptions were designed for. As a rule of thumb, if you expect something to happen *regularly*, you should handle it with explicit checks or alternative methods, not with try/catch.

Another benefit of the TryParse loop is that it keeps the error handling localized. In the try/catch version, the scope of the exception can be wider, if, for example, a different exception is thrown inside the try, it could accidentally be caught (if one isn’t careful to catch only `FormatException`). With `TryParse`, we specifically handle just the parsing outcome and nothing else.

### **Example 2: Parsing Multiple Values in Bulk**

Consider reading a list of strings and converting them to integers, where some inputs may be malformed. Using `int.TryParse` allows you to handle each conversion gracefully:
```csharp
string[] inputs = { "42", "19", "abc", "7.5", "100" };

foreach (string text in inputs)

{

    if (int.TryParse(text, out int num))

    {

        Console.WriteLine($"Parsed '{text}' as {num}.");

    }

    else

    {

        Console.WriteLine($"Could not parse "{text}" – not a valid int.");

    }

}
```
This will output:
```
Parsed '42' as 42.  

Parsed '19' as 19.  

Could not parse "abc" – not a valid int.  

Could not parse "7.5" – not a valid int.  

Parsed '100' as 100.
```
Every element is attempted, and we clearly handle the two cases (parsable or not) in a simple `if/else`. There’s no exception clutter, and the loop isn’t interrupted by a thrown exception. If we had used `int.Parse` in a try/catch for each element, two of those five parses would throw exceptions (for "abc" and "7.5"), which we’d catch to continue the loop. Aside from being slower (due to the thrown exceptions), that approach would make the code noisier. You’d either wrap the inside of the loop in a try/catch (with the catch perhaps just logging or counting an error), or wrap the whole loop and use some logic to continue after catching. Either way, it’s more complex than the clear TryParse approach.

The TryParse pattern scales much better in scenarios like this. If you have 1000 items and 200 are bad, you’ll handle 200 `false` returns quickly. With exceptions, you’d be throwing and catching 200 exceptions – incurring a large overhead and possibly cluttering logs or debug output with stack traces if not careful. By treating “not a number” as an expected branch, your code remains efficient and readable.

### **Example 3: Using Default Values on Parse Failure**

Another common scenario: you have an optional configuration or input, and if it’s missing or invalid, you want to use a default value instead of blowing up. With TryParse, this is easy:
```csharp
int port;

if (!int.TryParse(portString, out port))

{

    port = DEFAULT_PORT;

}

Console.WriteLine($"Server will run on port {port}.");
```
In one `if` block, we attempt to parse a string into an integer port. If it fails (perhaps the string was empty or not a number), we fall back to a predefined `DEFAULT_PORT`. No exception needed. The intent is crystal clear: *try to get a number, otherwise use default*.

The equivalent with exceptions would be:
```csharp
int port;

try

{

    port = int.Parse(portString);

}

catch (FormatException)

{

    port = DEFAULT_PORT;

}

Console.WriteLine($"Server will run on port {port}.");
```
In both the exception case, and the TryParse case, we have to show **how** to handle the control flow. If the value can’t be parsed, then do this. If there is an exception, then go over here. The Either monad means that a function can return an Either<int, Error> if it fails or succeeds. The control flow is the same, and the caller is forced to deal with it so-to-speak to retrieve the result, if there was a successful result. Remember for the Maybe monad, the monad dictates **how** the function is executed. The same way for the Either monad, if it was successful, then Map will execute. However, we now have two branches: right (success) and left (error.)

## **Either Monad for Expressive Error Handling**

The **Either** monad represents a value that can be one of two “types” – traditionally named `Left` and `Right`. By convention, **Right is the “successful” result** and **Left is the “error” result** (or reason for failure). You can think of `Either<Error, T>` as a container that either holds a `T` (in the Right case) or an `Error` (in the Left case). It’s similar to `Maybe<T>` but with an added dimension: if there’s no `T` value, we have something else (an error message, an exception, an error code, etc.) instead of just nothing.

In summary: Do the next step if everything’s okay; if an error occurred, short-circuit the chain.

In practical terms, an Either monad is a way of **returning errors from functions without throwing exceptions**. This aligns with the TryParse idea (no exceptions on expected failures), but in a more general and composable way. Instead of a method like `ParseInt(string)` throwing or returning a magic value on failure, we could have it return an `Either<string, int>`, meaning “either an int (on success) or a string error message (on failure)”. In the TryParse example, we had to specify **how** to handle the case where the value was incorrect.

Here is how one might model the Either monad. There is a lot of code, but it’s conceptually very similar to Maybe<T>. Exercise for reader: read the code, then try to rewrite it in your IDE. Remember that we need Unit and flatMap operations.
```csharp
public class Either<TFailure, TSuccess>

{

    private readonly bool _isSuccess;

    private readonly TFailure _errorValue;

    private readonly TSuccess _successValue;

    // Private constructor

    private Either(bool isSuccess, TFailure errorValue, TSuccess successValue)

    {

        _isSuccess = isSuccess;

        _errorValue = errorValue;

        _successValue = successValue;

    }

    // Unit: Factory for the error branch, we have to have a way to get a value into the Either monad

    public static Either<TFailure, TSuccess> Failure(TFailure error)

    {

        return new Either<TFailure, TSuccess>(false, error, default);

    }

    // Unit: Factory for the success branch, we have to have a way to get a value into the Either monad

    public static Either<TFailure, TSuccess> Success(TSuccess success)

    {

        return new Either<TFailure, TSuccess>(true, default, success);

    }

    // Map: apply f to the success value, or propagate error

    public Either<TFailure, TSuccess2> Map<TSuccess2>(Func<TSuccess, TSuccess2> f)

    {

        if (_isSuccess)

        {

            TSuccess2 result = f(_successValue);

            return Either<TFailure, TSuccess2>.Success(result);

        }

        else

        {

            return Either<TFailure, TSuccess2>.Failure(_errorValue);

        }

    }

    // FlatMap: chain a function that returns Either<Error, TSuccess2>

    public Either<TFailure, TSuccess2> FlatMap<TSuccess2>(

        Func<TSuccess, Either<TFailure, TSuccess2>> f)

    {

        if (_isSuccess)

        {

            return f(_successValue);

        }

        else

        {

            return Either<TFailure, TSuccess2>.Failure(_errorValue);

        }

    }

    // ToString: for debugging or law-checking

    public override string ToString()

    {

        if (_isSuccess)

        {

            return "Success(" + _successValue + ")";

        }

        else

        {

            return "Error(" + _errorValue + ")";

        }

    }

}
```
It’s pretty similar to the Maybe monad, but now there are two branches. Failure could be nothing, or Success could be nothing, but the monad enforces that either one must have a value. Although it’s idiomatic to put the error on the left hand side, it doesn’t really matter that much, Either doesn’t care.

We can use it like this:
```csharp
Either<string, int> ParseInt(string s)

{

    if (Int32.TryParse(s, out var n))

        return Either<string, int>.Success(n);

    else

        return Either<string, int>.Failure($"“{s}” is not a valid integer.");

}

// Chain two parses and add them:

Either<string, int> result =

    ParseInt("10")

      .FlatMap(n1 =>

         ParseInt("20")

           .Map(n2 => n1 + n2)

      );

// result.Match(

//    err => Console.WriteLine($"Error: {err}"),

//    sum => Console.WriteLine($"Success: {sum}")

// );

// → “Success: 30”
```
In our example, ParseInt has gotten pretty ugly. If we were in a functional language, then ParseInt would be a library function and would return Either<string, int> and we would not have to wrap Int32.TryParse.

This is a disadvantage when using an imperative language and shoehorning functional concepts. In Haskell, for example, it would be written as:
```
resultDo :: Either String Int

resultDo = do

  n1 <- parseInt "10"

  n2 <- parseInt "20"

  return (n1 + n2)
```
This is quite similar to using `TryParse`, but now the *error itself* is a first-class piece of data, not just an implicit false or an exception to catch. The caller is forced to handle both cases (since the `Either` type would make you check or pattern-match on its state). This explicitness can make the code more robust: you won’t accidentally ignore an error, because it’s in the return type, not off to the side.

The real power of the Either monad comes when **chaining multiple computations that each may fail**. With exceptions, if one function deep in a chain throws, you jump out to the nearest catch, which might be far away.
```csharp
static void ExceptionChainWithLocalCatch(string sA, string sB)

{

    // 1) Parse first number

    int a;

    try

    {

        a = int.Parse(sA);

    }

    catch (FormatException)

    {

        Console.WriteLine($"Error: '{sA}' is not a valid integer.");

        return;

    }

    // 2) Parse second number

    int b;

    try

    {

        b = int.Parse(sB);

    }

    catch (FormatException)

    {

        Console.WriteLine($"Error: '{sB}' is not a valid integer.");

        return;

    }

    // 3) Divide 100 by b

    int quotient;

    try

    {

        quotient = 100 / b;

    }

    catch (DivideByZeroException)

    {

        Console.WriteLine("Error: Cannot divide by zero.");

        return;

    }

    // 4) Format and print result

    string output;

    try

    {

        output = $"100 / {b} == {quotient}";

    }

    catch (Exception ex)  // unlikely, but illustrating a local catch

    {

        Console.WriteLine("Error formatting result: " + ex.Message);

        return;

    }

    Console.WriteLine(output);

}
```
With `Either` monads, you can chain operations in a controlled way such that if any step fails, the chain short-circuits, but you *stay* in the same flow structurally.

For example, say we want to take an input string, parse it to int, then divide 100 by that number. Using our `Either` monad:
```csharp
Either<int, string> outcome = ParseInt(userInput)

    .FlatMap(num => Divide(100, num));  // Suppose Divide returns Either<int,string> as well
```
Here, `ParseInt(userInput)` gives a `Either<int,string>`. We then `FlatMap` (bind) into `Divide(100, num)`, which might, for instance, return a failure if `num` was 0 (division by zero error). The beauty is that **`FlatMap` will only call `Divide` if the first result was a success. We do not need to tell it how to run ParseInt, Divide, etc.** If `ParseInt` failed, the FlatMap will just pass along the failure, skipping the `Divide` step entirely. The final `outcome` is again a `Either<int,string>`, which will be a success only if both steps succeeded, or a failure containing either the parse error or the division error (whichever happened first).

We would create a Match method in our Either monad:
```csharp
    public void Match(Action<TSuccess> onSuccess, Action<TFailure> onError)

    {

        if (_isSuccess)

        {

            onSuccess(_successValue);

        }

        else

        {

            onError(_errorValue);

        }

    }
```
We can then handle the `outcome` in one place:
```csharp
outcome.Match(

    success => Console.WriteLine($"Result: {success}"),

    error   => Console.WriteLine($"Error: {error}")

);
```
This **composability** is a major advantage. It keeps the error-handling logic local to where it’s needed and prevents deeply nested try/catch logic or error-code propagation. In essence, an Either/Result monad provides *structured error handling*. Each function in the chain doesn’t need to know what to do if the previous step failed – the monad takes care of propagating the failure forward, and the final consumer can deal with it appropriately. It’s akin to how `await` will propagate exceptions from an async method to where you await it, except with `Result` we propagate explicit error values.

To connect back to our earlier examples: using an Either monad is conceptually similar to the `TryParse` approach, but generalizes it. For instance, `int.TryParse` returns a bool and an out int. A `Either<int,string>` return value is like bundling those together: you either get an int or an error string. The monadic form just makes it easier to chain multiple operations. In a sense, `TryParse` and `TryGetValue` are *ad-hoc* implementations of the Either concept (with the error side being just an implicit “false”/failure). The Either monad formalizes it and lets you carry richer information on the failure side if needed.

## **Reader Monad for Dependency Injection (Deferred Context)**

The **Reader monad** (sometimes called the *Environment monad*) addresses a different scenario: computations that depend on some shared *environment* or configuration. In C# terms, this is very much like *dependency injection*. The Reader monad is similar, it lets you provide a function that takes in some environment/config `Env` and then return some output. It allows you to *defer providing the dependency* until a later stage. A function can be written *assuming* an environment will be available, and only when you actually run the computation do you pass in the real environment. In other words, we return a *function of the environment* as our result, to be executed once the environment is known.

Here's an example DI'ing a ficticious `PriceConfig` class via `IPriceConfig`:

```csharp
// 1) A pure configuration interface

public interface IPriceConfig

{

    decimal TaxRate { get; }

    decimal DiscountAmount { get; }

}

// 2) A simple config implementation (could come from appsettings.json, tests, etc.)

public class PriceConfig : IPriceConfig

{

    public decimal TaxRate { get; set; }

    public decimal DiscountAmount { get; set; }

}

// 3) A pure service—no logging, no repository, just a calculation

public class PriceService

{

    private readonly IPriceConfig _config;

    public PriceService(IPriceConfig config)

    {

        _config = config;

    }

    /// <summary>

    /// Applies discount then tax to the base price.

    /// Pure: always returns the same output for the same inputs.

    /// </summary>

    public decimal ComputeFinalPrice(decimal basePrice)

    {

        decimal afterDiscount = basePrice - _config.DiscountAmount;

        return afterDiscount * (1 + _config.TaxRate);

    }

}
```
There’s some wiring up, such as:
```csharp
services.AddSingleton<IPriceConfig>(new PriceConfig {

    TaxRate = 0.0825m,        // 8.25% tax

    DiscountAmount = 5.00m    // $5 off

});

services.AddTransient<PriceService>();
```
You don’t care which `PriceConfig` you get, it’s an `IPriceConfig`. The class doesn’t care, as it follows the same interface.

### **Implementing a Reader Monad in C#**

The `Reader` monad is very similar. We create a function that takes in some readonly environment `Env`, and outputs some result. Here is a function that takes in some readonly `Env` and outputs some result:

```csharp
public class Env
{
    public decimal TaxRate = 0.15;
    public decimal DiscountAmount = 1;
}

public decimal ComputeFinalPrice(Env env) {
    var basePrice = 10;
    decimal afterDiscount = basePrice - env.DiscountAmount;
    return afterDiscount * (1 + env.TaxRate);
}
```

**Hold on**, how do I pass in `basePrice`? We will have to refactor our `ComputeFinalPrice` method later on to use currying, because it is idiomatic to only take in a single argument at a time. If we add `decimal basePrice` along with our env, then it's no longer a Reader monad and we lose composability.

Let's continue. We can implement a generic `Reader<Env, T>` monad in C# to encapsulate this idea. It will hold an internal `Func<Env, T>` representing the computation. The monad’s `Unit` (or **Return**) operation will wrap a raw value into a `Reader` that takes in the environment, ignores it, and always returns that value. The `Map` and `FlatMap` (Bind) operations will thread the environment through. `Map` applies a transformation to the result *without* changing the environment, while `FlatMap` chains a new `Reader`-producing function, ensuring that each step of the chain sees the same environment value.

```csharp
public class Reader<Env, T>  
{  
    private readonly Func<Env, T> func;

    private Reader(Func<Env, T> func)  
    {  
        this.func = func;  
    }

    // Unit: wrap a value into a Reader that doesn't use the environment.  
    public static Reader<Env, T> Unit(T value)  
    {  
        return new Reader<Env, T>(env =>  
        {  
            return value;  
        });  
    }

    // Map: apply a function to the result inside the Reader context.  
    public Reader<Env, U> Map<U>(Func<T, U> transformer)  
    {  
        return new Reader<Env, U>(env =>  
        {  
            T originalValue = func(env);  
            U transformed    = transformer(originalValue);  
            return transformed;  
        });  
    }

    // FlatMap (Bind): chain a function that returns another Reader.  
    public Reader<Env, U> FlatMap<U>(Func<T, Reader<Env, U>> binder)  
    {  
        return new Reader<Env, U>(env =>  
        {  
            T originalValue      = func(env);  
            Reader<Env, U> next  = binder(originalValue);  
            U result             = next.func(env);  
            return result;  
        });  
    }

    // Run: finally supply the environment to get a concrete result.  
    public T Run(Env environment)  
    {  
        return func(environment);  
    }  
}
```

In summary: Any class you wire up once with its configuration via its constructor, then freely call its methods without re-passing that config, is literally using the Reader pattern. It's just a function that takes in some environment `Env`, and returns an output. In DI, it's typically a class that takes in some dependency/IRepository/IService, and outputs/does some output. The function doesn't care where `Env` is coming from, the same as the class doesn't care where the dependency/IRepository/IService is coming from, it just has it.

This `Reader<Env, T>` class is essentially a container for `Func<Env, T>`. Notice how `FlatMap` uses the same `env` to run the subsequent computation. This is what ensures the *same* context is threaded through all chained operations. With `Map` and `FlatMap` defined, `Reader` forms a proper monad (you could verify it satisfies identity and associativity laws, similar to our tests for `MaybeMonad`). In fact, many functional libraries simply define `Reader<Env, T>` as an alias for a function `Env -> T`, with monadic operations to compose those functions.

### **Using the Reader Monad for Configuration and DI**

The Reader monad shines when business logic depends on *read‑only configuration* that you don’t want to thread manually through every call.

Here’s that same explanation, but grounded in a concrete “price + tax” example:

Suppose you have a product whose base price is `100m`, and your “environment” just holds a tax rate:

 ```csharp
 public class TaxEnv { public decimal TaxRate { get; set; } }
 ```

 You can build a `Reader<TaxEnv, decimal>` that, when given an `env`, computes the price plus tax:

 ```csharp
 decimal basePrice = 100m;
 Func<TaxEnv, decimal> computeWithTax = env => basePrice * (1 + env.TaxRate);
 var taxReader = new Reader<TaxEnv, decimal>(computeWithTax);
 ```

 At this point, **nothing has run**—you’ve only wrapped up “given a tax rate, compute a taxed price,” just like DI holds your dependencies without executing any logic.

 Now imagine you want to turn that raw `decimal` into a formatted message. You call:

 ```csharp
 // transformer: decimal → string
 Func<decimal, string> formatter = total => $"Total with tax: {total:C}";
 var messageReader = taxReader.Map(formatter);
 ```

 Because you still haven’t provided an `env`, there’s **no** decimal to hand to `formatter`, so **`Map` doesn’t run**. Instead it builds and returns a **new** `Reader<TaxEnv, string>` whose `Run(env)` will do exactly two things in order:

 1. **Run** the original `computeWithTax` with your `env` to get a `decimal` taxed price.
 2. **Apply** `formatter` to that decimal to produce your final `string`.

 Only when you finally call:

 ```csharp
 string result = messageReader.Run(new TaxEnv { TaxRate = 0.15m });
 // result == "Total with tax: $115.00"
 ```

 will anything actually happen. This defers both the environment lookup **and** the formatting step until execution time—letting you compose multiple context-dependent transformations without manually threading `TaxEnv` through each one.


**Conclusion**

In Part 2 we moved beyond the “container” intuition and saw how monads let us **encode control‑flow concerns as data**:

1. **Maybe** became a *full* monad after we added `FlatMap`, proved the three monad laws, and generalized it to `MaybeMonad<T>`. Optional values are now composable instead of forcing scattered `if (x != null)` checks.

2. **Either / Result** showed how the same pattern cleanly expresses computations that may fail. By returning `Either<Error, T>`—rather than throwing exceptions—we can chain potentially‑failing steps while keeping both the happy path and the error path explicit and local.

3. **Reader** demonstrated that a monad can represent a *recipe* rather than a result. It defers the need for configuration or dependencies until the last moment, giving us pure functions that are easy to unit‑test and compose while still fitting naturally into C#’s DI ecosystem.

Across all three cases the theme is consistent:

*Write the business logic once; let the monad decide **whether**, **when**, or **with what context** the logic runs.*

Understanding these patterns pays off quickly: everyday tasks such as validating input, propagating errors, or threading configuration no longer bloat our code with boilerplate control flow.

Part 3 will pick up the “recipe” thread in earnest. We’ll look at monads like **`Task<T>`** (asynchronous workflows) and **IO/Effect** types, then show how to *compose* multiple concerns—e.g., asynchronous operations that can fail—without losing readability.

Until then, try sketching a few small utilities with `Maybe`, `Either`, or `Reader` in your own codebase. You’ll see how quickly the boilerplate melts away once the monad is doing the heavy lifting.

Part 3 coming soon.
