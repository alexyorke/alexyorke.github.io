---
title: "Embracing Functional Programming Principles in OOP with Static Factory Methods"
date: 2024-09-15
---

In functional programming, type safety ensures that values (often called "objects" in other programming paradigms) conform to the constraints defined by their type. This means that functions, data structures, and types can only hold and operate on values that are valid according to the rules of their type. By using constructs like algebraic data types, functional programming prevents the creation of invalid states. A number can only be a number, it can't be a string for example. So, if I have a function that accepts the Number type, then I know that it will be a number.

When we go into the day-to-day business side of things, things become less clear. For example, a customer's email is a string--sure, if my function expects the String type, then I'll get a string. But we have to do defensive validation, cluttering up our code with validation checks everytime we pass this mysterious customer email address string, that might not be valid.

In C#, we can simulate this type safetyness by using the static factory pattern. In this example, the ValidatedObject cannot be instantiated via new(), it must be through the factory. This gives a few advantages, namely, the object (or record in this case) cannot exist unless it is valid. Therefore, since it is also sealed, and immutable (as it is a record type), we don't have to constantly re-validate it.

Additonally, we get the bonus of being type safe. That is, say a method accepts two strings: a customer name and email. If it's typed as a CustomerEmail, then it is not possible to compile your code or get customer name and email mixed up in the method params.

```
public static partial class ValidatedObjectCreator
{
    internal sealed record ValidatedObject : IValidatedObject 
    {
        public string Data { get; }

        private ValidatedObject(string data) => this.Data = data;

        public static IValidatedObject Create(string data)
        {
            if (!IsValid(data)) throw new ArgumentException("Invalid input data.");

            return new ValidatedObject(data);
        }

        // Basic validation logic (can be customized)
        private static bool IsValid(string data) => data.Length > 3;

        public override string ToString() => Data;
    }

    internal interface IValidatedObject
    {
        static IValidatedObject Create(string data) => throw new NotImplementedException();
        // expose properties here as needed
    }
}


public static class Program
{
    public static void Main()
    {
        var validatedObject = ValidatedObjectCreator.ValidatedObject.Create("Test data");
        // this will fail
        // var validatedObject = new ValidatedObject("Test data");
    }
}
```
