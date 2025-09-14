---
title: "List is a monad (part 1)"
date: 2025-06-29
---

Note July 6th 2025: this post's original title was "A list is a monad". It has been changed to "List is a monad".

Note Sept 13 2025: this post has been revised based on the feedback from Hacker News.

The term “monad” is often invoked when describing patterns in functional programming. At the heart of monadic programming is sequencing computations, so each step can depend on the previous one while the monad threads context.

You may erroneously think all monads are containers, or burritos, or boxes. The **simplest** of monads can be [idealized](https://en.wikipedia.org/wiki/Idealization_%28philosophy_of_science%29) as a **container** (albeit a [flawed metaphor](https://byorgey.github.io/blog/posts/2025/06/16/monads-are-not-burritos.html)). Monads are much more than just containers, and there isn't the-one-and-only monad; instead it's better to think about them as a **programming pattern, recipe, factoring out control flow, or, in some cases, a deferred computation**. It depends on which monad you're talking about.

From a teaching perspective, to get the concept for what a monad is, we will start with the simplest of monads which will feel a lot like just a container but with some composable aspects. This provides the infrastructure to understand more complex monads later on.

## List: Map & flatMap in Practice

To an OOP developer, monadic types (`List<T>`) might look just like generics. It’s a typical pitfall to think “we have generics, so we have monads,” which isn’t true by itself. Monads do usually involve generic types, but they **require specific operations (`Unit` and `flatMap`) and the three monad laws on those types to ensure uniform behavior.** **This is key** and is fundamental to working with monads.

A good example of a monad is `List`. You’re likely very familiar with lists and working with lists.

The monad `Map` operation is responsible for:

* **Applying your function.** For `List`, `Map` runs `f` (a function) on *every* element. For example, let's define `f` as `f(x) = x + 1`. The list `[0,1,2,3]` becomes `[1,2,3,4]`. If the list doesn’t have any elements, then `Map` doesn’t call `f`. `f` doesn’t need to worry about that. Also, `f` doesn’t care if it’s `List<T>`; all `f` is, is just `f(x) = x + 1`. `Map` is responsible for running it.

* **Managing sequencing and combination.** The list context concatenates all results into one list (`Map` does **not** flatten any nested lists, `flatMap` is responsible for this). We don’t need to manually re-add elements via `Add` or otherwise manage the collection ourselves.

Notice that the monad in this case `List<T>` is responsible for running `f`. This shift means your business logic stays **declarative** and **composable**, you describe *what* happens to a single value, and the monad describes *how* and *when* it happens.

This is different from object-oriented and procedural programming because in those paradigms, if you want to process data, it is your responsibility to understand how to apply the function to your data. We have to use different control constructs to handle different types of data, and we’re also responsible for the “how”:

```csharp
public string f(string input) {  
  return input + " -appended text";  
}

// 1. List<string>: you must foreach and build a new list

var fruits = new List<string> {  
  "apple",  
  "banana",  
  "cherry"  
};

var newFruits = new List<string>();

foreach (var fruit in fruits)  
{  
  newFruits.Add(f(fruit));  
}

// 2. Single string: you must check for null first, then concatenate

string userInput = GetUserInput(); // could be null

if (userInput != null)  
{  
  userInput = f(userInput);  
}

// userInput could still be null here, or it could be the concatenated result

// 3. Dictionary<string, string>: you must know it’s key/value pairs

var dict = new Dictionary<string, string>  
{  
  ["a"] = "alpha",  
  ["b"] = "beta",  
  ["c"] = "gamma"  
};

// can’t modify while iterating, so capture keys first  
foreach (var key in dict.Keys.ToList())  
{  
  dict[key] = f(dict[key]);  
}
```

In these examples, we are forced to know **how** to update each structure procedurally. For a `List`, we have to call `Add`; for the `string` we can update it in place; for the `Dictionary`, we have to iterate over keys and update each entry. We have to know it’s a `List` beforehand to know to use `foreach`. We have to know it’s just a `string` to append another string to it.

With monads, you delegate the control flow to the monad itself, the monad knows how to update its underlying value(s). Recall that even the simplest monads **must implement two methods to be monads (`Unit` and `flatMap`) and must follow three monad laws.**

### `Unit`

**`Unit`** moves a raw value into the monadic context (this operation is sometimes called “lifting”, “identity”, “return”, “wrap”, or “promotion”, and in some libraries has names like `liftM` or `liftA`).

* In the list monad, **`Unit`** takes a single element and returns a list containing that element.

* For example, given the integer `1`, `Unit` produces a list as follows:

**Example (C#):**

```csharp
var list = new List<int> { 1 };
```

`List<T>` implements `Unit` because it allows moving a value into the mondaic context. Nothing about the value `1` changes, it’s simply wrapped in a `List`. If you access element `0` of that list, you get back `1`. That’s it.

---

### Map

**`Map`** applies a function to each value inside the monad.

In `List`, `Map` runs a function on every element and outputs a new list with that function applied to each element. Don’t overcomplicate it. For example, suppose we have a function that adds one, `f(x) = x + 1`. Passing this function to `Map` would simply add one to each element in the list. The list `[0,1,2,3]` would become `[1,2,3,4]`.

#### *Example (C#-ish):*

```csharp
var originalList = new List<int> { 0, 1, 2, 3, 4 };    
var mapped = originalList.Map(x => x + 1); // `Map` doesn’t exist in C# (use LINQ's `Select`), but assume this pseudocode
```

**Example (C#, without monads):**

```csharp
var originalList = new List<int> { 0, 1, 2, 3, 4 };    
var mappedList = new List<int>();

foreach (int x in originalList)    
{    
    mappedList.Add(x + 1);    
}
```

### How do you get the damn values out of the monads?

Ideally, you don’t want to pull the values out of a monad unless you absolutely have to. It’s possible to implement a `GetValue()` method that returns the underlying value, but once the value leaves the monadic context, we lose the benefits of that context and can no longer compose operations easily.

Think about `List<T>` as if you had never seen it before. You might say, “I don’t want my values trapped in this list, how am I supposed to use them?” and then manually extract each element into separate variables:

```csharp
// Pretend it’s your first time with List<T>
var numbers = new List<int> { 1, 2, 3 };

// --- Manual extraction (values “trapped” in the list) ---
var a = numbers[0];
var b = numbers[1];
var c = numbers[2];

// Now call your function separately on each:
var r1 = AddOne(a);
var r2 = AddOne(b);
var r3 = AddOne(c);
```

But by doing so, you lose the advantages of using a list in the first place: the ability to store arbitrarily long sequences, to pass around all the values together, to concatenate with other lists, and to iterate easily. If you want to add one to each item, extracting them one by one and handling each separately is tedious and error-prone.

Up to this point, monads might just seem like “fancy containers” that have to implement two odd methods (`Unit` and `flatMap`). Let’s explore a slightly more complex monad to see why they’re more than just containers.

## Maybe

Let’s consider a case where unwrapping the value may not always make sense. We’ll create a monad called `Maybe` (often also called an *Option*) which represents either an existing value or the absence of a value.

For simplicity, our `MaybeMonad` will hold an `int` internally (in a real library this would be a generic `Maybe<T>`). It’s not exactly a full monad yet, because we haven’t implemented `flatMap` on it.

```csharp
public class MaybeMonad {    
    private int value;    
    private bool hasValue;  

    // Unit    
    public MaybeMonad(int value) {    
        this.value = value;
        this.hasValue = true;
    }  

    // Unit (no value)
    public MaybeMonad() {
        // hasValue remains false by default
    }  

    // Map    
    public MaybeMonad Map(Func<int, int> func) {
        if (hasValue) {
            return new MaybeMonad(func(value));
        }
        return this;
    }
}
```

Here, the *`Unit`* operation corresponds to calling one of the constructors, that’s how we lift a raw value into a `MaybeMonad`. The *`Map`* operation might feel a bit strange because we’re just dealing with a single value (or none), whereas you might be used to mapping over a list of many values.

For example, to add 1 to a `MaybeMonad`:

```csharp
var age = new MaybeMonad(30);    
var newAge = age.Map(x => x + 1);    
// newAge now holds 31
```

Or if there was no value to begin with:

```csharp
var age = new MaybeMonad();    
var newAge = age.Map(x => x + 1);    
// newAge is still “nothing”, `Map` didn’t call `f(x)` because there was no value
```

This looks verbose just to add 1 to a number. Why wrap `30` in a `MaybeMonad` and call `Map` when we could have just incremented `30` directly? The point is that `age` is a `MaybeMonad`, by definition it might or might not contain a value. In the case where there is no value, `MaybeMonad`’s `Map` simply does nothing. You’d have to write the same conditional logic yourself in a procedural style:

```csharp
int? age = null;    
if (age != null) age++;
```

Or:

```csharp
int? age = 30;    
if (age != null) age++;
```

Now we start to see why a monad is not simply a container to be unwrapped at will. How would you “unwrap” a `MaybeMonad`? If it has a value, you could return it, sure. But if it doesn’t, there’s nothing to return, the absence itself is a meaningful state. `MaybeMonad` essentially encodes the idea of “nothing” (no result) in a way that isn’t just `null` (because in many languages `null` is still a concrete value of sorts). With `MaybeMonad`, if there’s no value, any function passed into `Map` simply won’t execute. Unwrapping it and getting a raw value out isn’t always meaningful in this context.

Another benefit of monads is that you can chain computations that themselves produce monadic results. The limitation of only having `Map` is that you might end up with nested monads. For example, imagine a function that returns a `Maybe<int>`. If you call `Map` on a `Maybe<int>` with that function, the result would be a `Maybe<Maybe<int>>`, a nested container, because the `Map` wraps the function’s `Maybe<int>` result into yet another `Maybe`. We need a way to apply a function that returns a monad and avoid this unnecessary nesting when chaining operations.

### flatMap

`flatMap` is like our `Map`, but it also flattens the result. **`flatMap` provides the ability to chain computations that themselves produce monadic values, which is the defining feature of monads.** For example, if you have a function that looks up a user and returns a `Maybe<User>`, but you want to pass it to another function that returns the user’s profile. Using `Map` would give you a `Maybe<Maybe<UserProfile>>`, an awkward nested container because the input would be a `Maybe<UserProfile>`. With `flatMap`, you both apply your lookup and collapse the layers in one go, so you can seamlessly sequence optional, error-handling, or asynchronous operations (e.g. promises/tasks) without ever wrestling with nested monadic types.

Here's what `flatMap` looks like:

```csharp
// Add this method inside MaybeMonad
public MaybeMonad FlatMap(Func<int, MaybeMonad> func)
{
    if (hasValue)
    {
        // Do not wrap again; let the callee decide whether to return a value or "nothing"
        return func(value);
    }
    // Propagate "no value"
    return this;
}
```

Use `flatMap` when your next step might also produce “no value,” and you want to keep chaining without ending up with `Maybe<Maybe<int>>`.

```csharp
Maybe<User> lookupUser(string id)  
{  
    // Imagine this calls a database or external service and returns Maybe<User>  
    return GetUserFromDatabase(id);  
}

Maybe<string> userIdMaybe = GetUserId();

// Using Map would yield Maybe<Maybe<User>> (nested) because lookupUser returns a Maybe<User>.  
// This quickly becomes unwieldy and makes further processing difficult.  
var nested = userIdMaybe  
    .Map(lookupUser);

// Using flatMap collapses the result to a single Maybe<User>  
var user = userIdMaybe  
    .FlatMap(lookupUser);
```

`flatMap` is arguably more important than `Map`, in fact, `flatMap` is required to qualify as a monad, and given `flatMap` you can implement `Map` in terms of it.

What does this chaining look like procedurally? It would be similar to:

```csharp
string userId = GetUserId(); // could be null  
if (userId == null) {  
  // e.g., return an error or stop here  
}

User user = GetUserFromDatabase(userId); // this could return null (no user found)  
if (user == null) {  
  // handle missing user  
} else {  
  // we have a valid user  
}
```

In the procedural version, we had to explicitly handle the control flow at each step (checking for `null` in this case). In the monadic version, the control flow is implicit in the monad. If `userIdMaybe` has no value, `flatMap` simply doesn’t call `lookupUser` at all, the “else do nothing” logic is built into `Maybe`.

In the monadic example, you could write:

```csharp
Maybe<string> userIdMaybe = GetUserId();  
Maybe<User> userMaybe = userIdMaybe.FlatMap(lookupUser);
```

The monads handle the control flow for us. `GetUserId()` returns a `Maybe` because we’re acknowledging the user ID might not exist. We’ve defined the `Maybe` monad such that if there’s no value, any subsequent function (like `lookupUser`) won’t execute. There’s nothing mystical here, we explicitly designed `Maybe` to work that way.

This is why it makes sense to wrap values in monads and keep chaining within the monadic context: you can sequence operations (like getting a user ID, then looking up a user, then perhaps fetching their profile) without writing a single explicit `if` or loop for the control flow. Each monad step handles the logic of “if there’s no value, stop here” automatically.

If you prematurely yank a value out of a monad, you end up doing manual work that defeats this benefit. For instance, consider if we had a `GetValue()` method to extract the inner value (with `null` representing “no value”):

```csharp
Maybe<string> userIdMaybe = GetUserId();  
var actualUserId = userIdMaybe.GetValue();  
if (actualUserId != null) {  
    // do something with actualUserId  
}
```

Eww. If we treat the monad as just a fancy wrapper to put a value in and then take it out immediately, it does feel like pointless ceremony. This is where many people give up on learning monads, it seems like you’re just putting a value in a box and taking it out again with extra steps. But the power of monads comes when you stay *inside* the monadic context and keep chaining operations. In Part 2, we’ll look at more advanced monads that aren’t just simple containers, and you’ll see how staying in the monadic pipeline pays off.

## **Closing the loop on Maybe**

We’re making a few changes to the `Maybe` monad to give it a more official, ergonomic API. First, instead of letting callers construct the underlying representation directly, we’ll expose two *factory methods*: `Some` and `None`. Second, we’ll generalize map: instead of only mapping over integers, the monad will be generic so it can map any type. Finally, we’ll standardize the name to `Maybe<T>`. Together, these tweaks clean things up and make the monad easier to use across more scenarios.

```csharp
public sealed class Maybe<T>
{
    private readonly bool _has;
    private readonly T _value;

    private Maybe(T value)
    {
        _has = true;
        _value = value;
    }

    private Maybe()
    {
        _has = false;
        _value = default(T);
    }

    public static Maybe<T> Some(T value)
    {
        return new Maybe<T>(value);
    }

    public static Maybe<T> None()
    {
        return new Maybe<T>();
    }

    public Maybe<U> Map<U>(Func<T, U> f)
    {
        if (_has)
        {
            return Maybe<U>.Some(f(_value));
        }
        return Maybe<U>.None();
    }

    public Maybe<U> Bind<U>(Func<T, Maybe<U>> f) // aka FlatMap
    {
        if (_has)
        {
            return f(_value);
        }
        return Maybe<U>.None();
    }
}
````

To wrap up **`Maybe`**: it’s perfect when you only need to model “value or no value.” Often, we also need to know *why* a value is missing (not found, invalid input, business‑rule violation). **`Maybe`** can’t carry that reason.

## Monad Laws

To be a true monad, a type must not only provide `Unit` and `flatMap` operations, but also obey three simple laws that make sure these operations behave consistently:

1. **Left Identity:** `Unit(x).flatMap(f)` is the same as `f(x)`. (Wrapping a value and then immediately applying a function to it is equivalent to just calling the function on the raw value.)
2. **Right Identity:** `m.flatMap(Unit)` is the same as `m`. (If you `flatMap` a monad with the `Unit` function, the monad should remain unchanged.)
3. **Associativity:** `m.flatMap(f).flatMap(g)` is the same as `m.flatMap(x => f(x).flatMap(g))`. (It doesn’t matter how you parenthesize nested `flatMap` operations, the outcome will be the same.)

You don’t need to memorize these laws, but they provide a mathematical guarantee that monadic operations will compose reliably. Our `MaybeMonad` adheres to these laws, making it a true monad.

As we’ve seen, monads provide a context for computation. By defining two core operations, `Unit` (to wrap a value) and `flatMap` (to sequence operations that produce a new context), we abstract away manual control flow like loops and null-checks. This lets us turn scattered procedural code into a single declarative pipeline.

The real power comes when we apply this pattern to different contexts. In Part 2, we’ll explore other useful monads, like `Either` for more descriptive error handling, and see how to combine monads to manage multiple concerns at once.

Exercise for reader: I'd encourage opening up your IDE, without any AI assistance, and implementing the `Maybe` monad from scratch (no cheating.)

[Part 2](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result-either)
