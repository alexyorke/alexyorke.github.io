---
title: "A list is a monad"
date: 2025-06-29
---

# A list is a monad

The term “monad” is often invoked when describing patterns in functional programming. Yet explanations typically swing between high-level metaphors and deep mathematical abstractions. Each approach offers part of the picture, intuition without precision, or rigor without intuition but seldom both.

Monads can be [idealized](https://en.wikipedia.org/wiki/Idealization_%28philosophy_of_science%29) as a **container** (albeit is [a flawed metaphor](https://byorgey.github.io/blog/posts/2025/06/16/monads-are-not-burritos.html)) or context holding a value (or multiple values, or no value), **but in some cases we will get into later on** it’s better to think of it as a **recipe** or **deferred computation** for producing a value. At the heart of monadic programming is the idea that you write **one** function, say, `f(x) = x + 1`, and then **reuse** it across different contexts without rewriting control-flow logic.

## Two Flavours: Result vs Recipe

While all monads provide a computational context, they generally fall into two flavors:

* Monads as "Results": These represent a value that has already been computed, but with extra context. List<int> is a result with the context. Maybe<int> is the result of a computation with the context of "possible optionalness." For these, the "container" metaphor is a useful, if limited, starting point.  
* Monads as "Recipes": These represent a computation that has not happened yet. They are a blueprint for producing a value. C#'s Task<T> is a perfect example: it doesn't hold a value, it holds the promise of a value to be computed asynchronously. For these, the "recipe" metaphor is a much better fit. Unwrapping a task doesn’t give you the computed result, it just gives you the instructions **to** compute it.

Sometimes, you can mix the flavors. In this post, we will focus on the first category to build our core intuition. We'll start with List and Maybe to understand the mechanics of map and flatMap on concrete results. In Part 2, we'll see how these same patterns unlock immense power when applied to "recipe" monads like Task.

## List<T>: Map & FlatMap in Practice
To an OOP developer, monadic types (List<T>) might look just like generics. It’s a typical pitfall to think “we have generics, so we have monads,” which isn’t true by itself. Monads do usually involve generic types, but they **require specific operations (Unit and flatMap) and the three monad laws on those types to ensure uniform behavior.** **This is key** and is fundamental to working with monads.

A good example of a monad is a list. You’re likely very familiar with lists and working with lists.

The monad Map operation is responsible for:

* **Applying your function. List:** Map runs `f` on *every* element, so the list [0,1,2,3] becomes [1,2,3,4]. If the list doesn’t have any elements, then, well, Map doesn’t call f. f doesn’t need to worry about that. Also, f doesn’t care if it's a list, all f is, is just f(x) = x + 1. Map is responsible for running it.  
* **Managing sequencing and combination.** The list context concatenates results into one list. We don’t need to manually modify or re-add elements to the list via .Add.

Notice that the monad is responsible for running f(x). This shift means your business logic stays **declarative** and **composable**, you describe *what* happens to a single value, and the monad describes *how* and *when* it happens.

This is different from OO and procedural programming because in procedural programming, if you want to process data, it is your responsibility to understand how to apply the function to your data. We have to use different control constructs to handle different types of data, and are also responsible for the “how”.

Here’s examples in C#:

```
const string suffix = " - appended";

// 1. List<string>: you must foreach and build a new list

var fruits = new List < string > {
  "apple",
  "banana",
  "cherry"
};

var newFruits = new List < string > ();

foreach(var f in fruits)

{

  newFruits.Add(f + suffix);

}

// 2. Single string: you must check for null first, then concatenate

string maybeText = GetUserInput(); // could be null

if (maybeText != null)

{

  maybeText = maybeText + suffix;

}

// 3. Dictionary<string,string>: you must know it’s key/value pairs

var dict = new Dictionary < string,
  string >

  {

    ["a"] = "alpha",

    ["b"] = "beta",

    ["c"] = "gamma"

  };

// can’t modify while iterating, so capture keys first

foreach(var key in dict.Keys.ToList())

{

  dict[key] = dict[key] + suffix;

}
```


In this example, we are forced to deal with knowing **how** to procedurally update these structures. For a list, we have to call Add, for the string, we can update it in place, for the dictionary, we have to access the keys. We have to know it’s a list beforehand so we know to use foreach. We have to know it’s just a string to append another string to it. We have to know it’s a dictionary to know how to iterate and update its keys. You can clean it up a bit, and make a function like the following:

```
public string AppendText(string input) {

  if (input != null) return input + “ -appended text”;

  return “ -appended text”;

}
```

But you still need to foreach, loop, etc. Instead, monads delegate control flow to itself and are responsible for knowing how to update the underlying value(s). Recall, however, that even the simplest of monads (essentially containers) **must implement two methods in order to be monads (Unit and flatMap), and also follow three monad laws.**

### **Unit**

**Unit** moves a raw value into the monadic context, sometimes called “lifting”, “identity”, “return”, “wrap”, or “promotion”, or some fancy operation names like “liftM” or “liftA”.

* In the list monad (let’s just call it a list), **Unit** takes a single element and returns a list containing that element.

* For example, given the integer `1`, Unit produces a list via:

**Example (C#)**

```
var list = new List<int> { 1 };
```

Nothing about the value `1` changes, it’s simply wrapped in a list. If you access element 0 of that list, you get back `1`. That’s it.

---

### **Map**

**Map** applies a function to each value inside the monad.

In the list, Map runs a function on every element and outputs a new changed list with that function applied to each element. Don’t overcomplicate it. For example, say there is a function that just adds one to its input, for example f(x) = x + 1. Then, passing this function to Map would simply add one to each element in the list. The list [0,1,2,3] would become [1,2,3,4].

#### **Example (C#):**

```
var originalList = new List<int> { 0, 1, 2, 3, 4 };  
var mapped = originalList.Map(x => x + 1); // Map doesn’t exist in C# (and instead is called Select in LINQ) but just use this as pseudocode
```

**Example (C#, procedural):**
```
var originalList = new List<int> { 0, 1, 2, 3, 4 };  
var mappedList = new List<int>();

foreach (int x in originalList)  
{  
    mappedList.Add(x + 1);  
}
```

### How do you get the damn values out of the monads?

You kind of don’t really want to take them out per-se, unless required. It’s possible to implement a GetValue() method that just returns the underlying value, but when the value leaves the monadic context, we lose its benefits and can no longer compose them.

Recall that a list is a monad, and pretend that it’s your first time using a list. You might say, I don’t want my values trapped in this list, how am I supposed to use them? Then proceed to take them out as separate variables and pass them around individually.

```
// Pretend it’s your first time with a List<T>  
var numbers = new List<int> { 1, 2, 3 };

// --- Manual extraction (values “trapped” in the list) ---  
var a = numbers[0];  
var b = numbers[1];  
var c = numbers[2];

// You’d then have to call your function separately on each:  
var r1 = AddOne(a);  
var r2 = AddOne(b);  
var r3 = AddOne(c);
```

But in doing so, you lose the advantage of lists, that is, the ability to store arbitrarily long sequences, the ability to pass all of the values at once, to concatenate with other lists, and the ability to iterate through the items. If you want to add one to each of the items, then you’ll have to individually address each variable and add one to it. It’s very tedious.

## Maybe<T>
Let’s move to a slightly more complex example where it may not always make sense to unwrap or “get at” the underlying value. Let’s create a monad called “Maybe”, which holds an already-computed result (or the absence of one.)

For simplicity, our MaybeMonad will hold an int, but in a real-world library, this would be a generic Maybe<T>.

```
public class MaybeMonad {  
    private int value;  
    private bool hasValue;  
      
    // Unit  
    public MaybeMonad(int value) {  
        this.value = value;  
        this.hasValue = true;  
    }  
      
    // Unit  
    public MaybeMonad() {  
          
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

Example (assume f(x) = x + 1):

```
var age = new MaybeMonad(30);  
var newAge = age.Map(x => x + 1);  
// newAge is now 31
```

Or,
```
var age = new MaybeMonad();  
var newAge = age.Map(x => x + 1);  
// newAge is still nothing, Map decided it should not run f(x) because there is no value
```

Procedurally, we would have written an if statement to check if there was a value, then update it conditionally. So, we would have to be responsible for **how** to run this function:

```
int? age = null;  
if (age != null) age++;
```

Or,
```
int? age = 30;  
if (age != null) age++;
```

We can start to see why a monad is not simply a container, or something to be unwrapped. How does one unwrap a MaybeMonad? If it has a value, it’s straightforward, just return the value. If there isn’t a value, then, well, there’s nothing in the container. “Nothing” is an abstraction the MaybeMonad defines, it isn’t representable via null because null is something, it is null. MaybeMonad defines that no computations can run in the case that a value does not exist. This is where unwrapping the container, or a box doesn’t always make sense.

This means that you can chain computations that themselves return Maybes, then compose them. The issue with only having Map is that we may end up with extraneous nested containers. For example, let’s say a function returns a Maybe<int>. If we chain it with Map, then the input to that function is also a Maybe<int>, which itself gets wrapped into a Maybe, giving a <Maybe<Maybe<int>>. We need another way to chain the computations, but to avoid having the unnecessary nested containers as we compose monads.

### **flatMap**

flatMap is like our Map, but it also flattens the result. **flatMap provides the ability to chain computations that themselves produce monadic values, which is the defining feature of monads.** For example, if you have a function that looks up a user and returns a Maybe<User>, but you want to pass it to another function that returns the user’s profile. Using Map would give you a Maybe<Maybe<UserProfile>>, an awkward nested container because the input would be a Maybe<UserProfile>. With flatMap, you both apply your lookup and collapse the layers in one go, so you can seamlessly sequence optional, error-handling, or asynchronous operations (e.g. promises/tasks) without ever wrestling with nested monadic types.

```
// lookupUser: string → Maybe<User>  
Func<string, Maybe<User>> lookupUser = id => GetUserFromDatabase(id)  
    /* returns a Maybe<User>, empty if not found */;

// Map gives Maybe<Maybe<User>> (nested container) because LookupUser returns a Maybe<User>  
// This quickly becomes unwieldy, and these nested containers do not help us and make it difficult to process values later on  
var nested = userIdMaybe  
    .Map(lookupUser);

// flatMap collapses it to Maybe<User>  
var user = userIdMaybe  
    .FlatMap(lookupUser);
```

flatMap is arguably much more important than Map, in fact, flatMap is a requirement to implement a monad and itself can implement Map.

Procedurally, it might look like this:

```
string userId = GetUserId(); // could be null  
if (userId == null) {
  // throw an error, stop, etc.  
}

var user = GetUserFromDatabase(userId); // user is a User or null  
if (user == null) {
  // error here  
} else {
  // user is valid  
}
```

In the procedural example, notice that we have to specify the control flow ourselves, however, in the monadic example, control flow is implied through the monads. If userIdMaybe doesn’t contain a value, then flatMap just doesn’t execute lookupUser.

## Monad Laws

To be a true monad, a type must not only have Unit and flatMap operations but also obey three simple laws. These laws ensure that chaining operations behaves predictably.

1. Left Identity: Unit(x).flatMap(f) is the same as f(x). (Wrapping a value and then immediately applying a function is the same as just applying the function to the value).  
2. Right Identity: m.flatMap(Unit) is the same as m. (Applying the simplest possible wrapping function shouldn't change the monad).  
3. Associativity: m.flatMap(f).flatMap(g) is the same as m.flatMap(x => f(x).flatMap(g)). (The order in which you group chained operations doesn't matter).

You don't need to memorize these, but they are the mathematical guarantee that allows monads to be composed so reliably. Our MaybeMonad follows these laws, making it a true monad.

We've seen how monads provide a context for computation. By defining two core operations, Unit (to wrap a value) and flatMap (to sequence operations that return a new context), we can abstract away control flow like loops and null-checks. This turns scattered procedural code into a single, declarative expression.

The real power comes from applying this pattern to different contexts. In Part 2, we'll explore other useful monads like Either for more descriptive error handling and see how to compose them together to manage multiple concerns at once.

Part 2 coming soon.
