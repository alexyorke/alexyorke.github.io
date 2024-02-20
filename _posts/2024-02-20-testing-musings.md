---
title: "Testing musings"
date: 2024-02-20
---

This is an exerpt from my book, Beginning CI/CD. This is a pre-pre-pre manuscript, so it's pretty messy.


[[https://www.youtube.com/watch?v=lDG1KVrO8X0&t=162                   
 7s]{.underline}](https://www.youtube.com/watch?v=lDG1KVrO8X0&t=1627s) 
                                                                       
 In this company, 95% of the issues found by the UI automated tests    
 were data errors, like getting 2.21 instead of 2.22. These errors     
 come from backend calculations, not the UI. Using slower E2E tests    
 for these isn\'t efficient. It\'s better to use unit tests that focus 
 on these calculations. This approach makes testing quicker and gives  
 developers faster feedback.                                           
                                                                       
 Key point is: make sure to track the failures for the tests, and why  
 they failed. Test at the level where it makes sense. 


## Testing


1.  ### Introduction

    1.  Testing is about providing a holistic interpretation of the
        extent that the application can reliably achieve a user's
        goal(s). Tests are only as good as the effort you put into them.

    2.  Testing is mostly about finding defects; however, it is a very
        broad and large topic and encompasses multiple facets of
        software development, such as quality, usability, performance,
        etc., some of which are considered "checking," which are
        operations that can be performed by a computer (i.e.,
        demonstrations). Demonstrations are things that are known to be
        true, and the computer verifies if it still holds true.

    3.  Software can\'t be completely bug-free because humans,
        libraries, and hardware are not perfect. Therefore, testing
        focuses on making software work well for users\' needs and
        business goals, rather than removing all bugs.

    4.  ![A road with a guard rail Description automatically
        generated](vertopal_7cf17b12d305426e8597d711f8f376f6/media/image1.png){width="5.616833989501313in"
        height="4.2126257655293085in"}

    5.  [[Guardrail -
        Armtec]{.underline}](https://armtec.com/specialty-products/guardrail/)

    6.  Testing typically refers to the structured evaluation of
        software against set criteria, often using automated tests. When
        people claim they \"don\'t test\", they usually mean they lack a
        formal testing plan or automation. However, even basic actions
        like compiling software or navigating a post-deployment website
        are forms of testing. Software use, whether by developers or
        customers, inherently involves testing. If no one interacts with
        or notices issues in the software, its value and relevance are
        questionable.

    7.  Testing is like guardrails. It helps ensure that a certain path
        is taken but cannot guarantee it. Having too many guardrails
        makes it difficult to change the path in the future (e.g.,
        changing features or adding new ones.) Having too few means it
        is difficult to assess the impact of changes in complex
        programs. It is very important to know how "tight" to make your
        tests.

    8.  Automated testing in CI/CD provides a rapid feedback loop,
        allowing developers to quickly verify their changes without
        disrupting the system. Tests are run before and sometimes during
        integration, ensuring they are reliable since a failed test can
        halt deployment. This efficiency means developers swiftly catch
        errors, speeding up development, leading to higher-quality
        products for customers, and freeing QA to focus on more complex
        issues.

    9.  Some of the types of testing are: unit testing, integration, E2E
        (end to end), etc. It's important to know when to use each type
        of test, because it can help provide a better picture on how
        your application performs in the real world.

    10. Going forward, I will split testing up into two categories:
        automated testing and manual testing. This is, technically, a
        false dichotomy however. The reason why it is split is because
        automated testing can be run on CI/CD runners, while manual
        testing cannot. I will use the terms in this way to refer to it
        like that. Automated testing is a core part of CI/CD, and
        contributes to a fast feedback loop that allows developers to
        derisk their changes.

    11. Writing tests is not a one time ordeal. Tests constantly evolve
        with the application.

    12. Tests are normally written when a feature is created, and are
        part of the PR to be reviewed. Tests should be reviewed with the
        same scrutiny as the feature code.

    13. Testing is useful when the system is too large to be able to
        effectively reason about your changes. There has to be some
        testing done for a feature; otherwise, there is no evidence that
        it exists. There must be a chain of integrity. Tests are
        designed to keep things the way they are. With constant
        evolutionary designs and changes, it means that it can drag down
        development. There has to be some balance between writing tests
        and code because it isn't possible to test code 100%. Therefore,
        you'd be writing tests for an infinite time. There has to be a
        certain value derived in testing. It's about writing useful
        tests, if you are going to write tests. It's also about knowing
        what to test and the important things to test that might not
        change often. There is a certain amount of complexity that can't
        be architected away, and thus, tests are useful for managing
        that, the inter-relatedness between modules that would otherwise
        have developers having to do the tests themselves or spend an
        inordinate amount of time tracing through the code, which would
        be very error-prone.

    14. What is quality?

        1.  [[Why Quality? \| Concerning
            Quality]{.underline}](https://concerningquality.com/why-quality/)

        2.  Quality is subjective, rooted in the alignment of perceived
            expectations with actual standards. It is inherently
            dynamic, shifting according to the expectations and
            standards at play in any given scenario.

        3.  Quality involves a degree of ethics, as it implies that the
            product is being sold in good faith. This aspect is
            particularly important in scenarios where the actual quality
            cannot be immediately assessed by the consumer.

        4.  The perceived quality of a product or service can impact the
            seller\'s reputation, affecting the customers\' trust and
            influencing their decision-making regarding future
            purchases.

        5.  The utility of a product and its ability to meet or exceed
            expectations is also an aspect of quality. Too much
            deviation from expectations, however, can lead to negative
            outcomes.

        6.  The lifetime or the existence of the product doesn\'t
            necessarily relate to its quality. A product may not exist
            perpetually but still provides value. Also, quality can
            intangibly improve other products\' quality.

        7.  Testing ensures that the product meets the expectations of
            its users. It verifies that the product solves the problem
            for which it was intended, fulfilling its purpose.

        8.  The utility of a software product, for example, isn\'t
            erased even if the software gets deleted. The software might
            have solved problems in the past, and that usefulness is
            immutable.

        9.  Software that serves no purpose currently might still be
            valuable for potential future use, like mitigating risks or
            proving useful in audits. This aspect also speaks to the
            subjective nature of quality.

    15. Writing tests should not be akin to eating your vegetables. You
        write them because they have utility. It is not efficient to do
        all of the testing manually. And you have to have a certain
        level of confidence that your feature doesn't break something
        else somewhere in the application (that you might have not known
        about). Large applications are especially difficult to hold the
        entire thing in your head.

2.  ### Precedent

    1.  What is a test fixture? It has its roots in hardware, where a
        literal, physical test fixture was used to mount the hardware
        and prepare it for testing.

    2.  ![A close-up of a machine Description automatically
        generated](vertopal_7cf17b12d305426e8597d711f8f376f6/media/image2.png){width="3.151042213473316in"
        height="3.786979440069991in"}

    3.  [[Electronic test fixture design \|
        Bloomy]{.underline}](https://www.bloomy.com/media-gallery/detail/246/236)

    4.  In software, this is used as a base environment where different
        states are set up, like variables, globals, databases, etc. and
        are usually prepared such that the tests can easily access the
        state.

    5.  A mock literally means a replica, or something that is like
        something else, but not exactly. For example, in hardware it
        might be a stand-in, or an object that performs some of the
        functionality but not all of the item that it is mocking. This
        is useful as the original hardware might be expensive, and many
        copies cannot be created purely for testing. In software
        development, mocking is used to refer to creating a function
        that is called instead of what you're trying to call, usually to
        avoid high overheads or expensive state management. This
        function is created by the user, and pretends to function as the
        original call, and can return and accept values and perform any
        processing desired on the data, usually less processing than
        what it is mocking.

    6.  ![A yellow rubber ducky Description automatically
        generated](vertopal_7cf17b12d305426e8597d711f8f376f6/media/image3.png){width="2.646351706036745in"
        height="3.0064424759405073in"}

    7.  In this case, the rubber duck is used in place of a real duck.

    8.  

    9.  \*\*1960s-1980s: Hardware Testing Era\*\*

    10. \- \*\*1960s:\*\* The concept of test fixtures originates from
        the hardware domain. Physical test fixtures are designed to hold
        the hardware securely and ensure it\'s positioned correctly for
        testing. They are particularly common in the electronics
        manufacturing industry, where they ensure consistent and
        reliable testing of circuit boards and other electronic
        components.

    11. \- \*\*Late 1970s:\*\* With the advent and growth of personal
        computing, there\'s a significant push towards more complex
        electronics and, consequently, more advanced test fixtures. This
        era marks a distinction between simple, manually-operated test
        fixtures and the more complex, automated fixtures.

    12. 

    13. \*\*1980s-1990s: Birth of Software Testing Tools\*\*

    14. \- \*\*1980s:\*\* As software becomes more intricate, the idea
        of setting up a standard environment or \"fixture\" for testing
        software starts to emerge. It's based on the concept from the
        hardware domain but adjusted for the software paradigm.

    15. \- \*\*Late 1980s to Early 1990s:\*\* The concept of \"mock
        objects\" begins to emerge in the software domain. Developers
        realize that they need a way to test software components in
        isolation, without needing to use the real resources (like
        databases or third-party services) they interact with.

    16. 

    17. \*\*2000s: Growth and Maturation of Software Testing
        Frameworks\*\*

    18. \- \*\*Early 2000s:\*\* Software testing tools and libraries
        like JUnit for Java introduce the idea of \"test fixtures\" as a
        formal concept in software testing.

    19. \- \*\*Mid-2000s:\*\* Mocking libraries, such as Mockito for
        Java and Moq for .NET, gain popularity. They provide a
        systematic way to replace real objects with simulated ones for
        testing, reflecting the "mock" concept from the hardware domain.

    20. \- \*\*Late 2000s:\*\* As agile methodologies and test-driven
        development (TDD) become more prevalent, the use of test
        fixtures and mocks becomes even more common. This is due to the
        emphasis on writing tests before actual code, and the need for
        isolated, quick tests.

    21. 

    22. \*\*2010s: Integration and Acceptance Testing\*\*

    23. \- \*\*Early 2010s:\*\* With the rise of microservices and
        distributed systems, the need for integration testing grows.
        Tools like Postman and WireMock emerge, allowing testers to mock
        entire services or APIs.

    24. \- \*\*Mid to Late 2010s:\*\* Concepts like Behavior-Driven
        Development (BDD) emerge, leading to the growth of tools like
        Cucumber and SpecFlow. These tools focus on writing tests in a
        more human-readable format and often employ fixtures and mocks
        to simulate real-world scenarios.

    25. 

    26. \*\*2020s: Shift-Left and Modern Testing Paradigms\*\*

    27. \- \*\*Early 2020s:\*\* The \"shift-left\" testing paradigm
        starts gaining traction. The idea is to introduce testing as
        early as possible in the software development lifecycle, leading
        to the development of more tools that integrate with CI/CD
        pipelines.

3.  ### The Role and Purpose of Tests

    1.  Testing exists because systems and humans are fallible. If we
        truly always knew the exact intent of our changes and precisely
        if they were desired, then tests would not be needed. This is
        because tests are designed to check invariants. In a way, if you
        knew precisely what the test was, then therefore you would not
        have to test it because you would be implicitly doing the
        testing by verifying that the changes align with expected
        behavior.

    2.  Some types of tests assume that all changes to software that do
        not align with the test are unwanted. These tests are usually
        very concrete and small, for example, unit tests. For example,
        if an invariant is no longer met, then it could have meant that
        a bug was introduced into the function, or, there was a feature
        change that caused the function to return different output to
        accommodate different scenarios. ThThe tests doesn't know
        that.This may or may not be a good thing, depending on your
        stage of product (e.g., a fast-moving startup that changes often
        may have to rewrite tests many times, thus reducing their
        purpose.)

    3.  Tests provide information on whether the previously defined
        contracts have been violated and let the programmer decide. It
        is not normally possible for one person to fully understand the
        full cause-and-effect of their changes throughout the entire
        system.

    4.  Testing prevents unwanted changes, but the definition of what
        changes are unwanted are only specified by the test coverage and
        cases.

    5.  In very large systems, it may not be possible to fully reason
        about how your change will impact the entire system. Therefore,
        tests prevent excessive change.

    6.  Tests slow down the development process in exchange for higher
        resilience and preventing unintended changes. Tests assume that
        the app will remain constant (within a tolerance threshold), so
        there will always be some push-and-pull; apps normally require
        adding features for stakeholders or through security updates
        (deprecating legacy software, requiring refactoring.)

    7.  Slowing down a process isn't necessarily bad. It depends on what
        value it brings.

    8.  It can help with increasing speed long-term, as it can prevent
        re-work of code that has to be rewritten.

    9.  Tests assume that tests do not slow down the development process
        overall, and in fact increase the speed of development, as
        rework due to broken features is more costly to fix in
        production vs. fixing once it was introduced. This depends on
        how quickly the tests run and how much risk the app is willing
        to take.

    10. Counter argument: assume the tests ran instantaneously and
        required no computational resources. Then, the output of the
        test is considered information. This information must be
        processed or acted upon in some way, otherwise testing is not
        useful. This is because the act of simply running a test doesn't
        do anything, its computations are not used by customers and the
        business usually does not retain its computational state.
        Therefore, testing must slow down the process, because the
        information from the tests must impact decision making or the
        outcome of the software.

    11. Counter-counter argument is: the act of writing tests, even if
        the fact that they have failed is discarded is still useful,
        because it makes developers able to gain a better understanding
        of the code, and can be used for documentation purposes.
        However, in order to gain an understanding of the code, you have
        to verify if the test case works, therefore, it goes back to the
        fact that information derived from tests is necessary, so you
        have to know if it failed.

    12. Whether intent is preserved through code changes (e.g., I change
        the color of a button, therefore that button's color should be
        changed, not the background color of the page)

    13. The entire app is a function, and the function must produce
        expected outputs within a tolerance given a set of inputs (or
        mutate state)

    14. To check if users can complete a goal or goals successfully

    15. It doesn't matter how many API tests succeeded, if the user
        cannot complete their goal (with appropriate state changes),
        then the app is useless

    16. Goals aren't always 100% aligned. Consider auditing requirements
        or telemetry. If these aren't performed, customers don't care
        but the business does.

    17. If usability, performance, clarity, and relevance are previously
        established in a prior version of the application, then a proxy
        for maintaining those is that the app must remain the same (thus
        keeping its goals.)

    18. CI/CD can make testing more difficult due to the constant flow
        of changes. It might be unreasonable to do testing prior to
        releases, as this would be a bottleneck for the releases, as
        they are continuous. It also might put additional pressure on
        the QA team, as they would be unable to fully understand the
        full extent of the changes.

    19. You have to be able to have a developer's workspace locally, and
        be able to test locally. By locally, I mean on your computer,
        but that is allowed to contact other servers. It should be fast,
        i.e., there should be some sort of isolated environment (perhaps
        locally, perhaps on another server) where you can test.

    20. Depending on your project type, it might require different
        commands to test the project. Here are a few.

  --------------------------------- -------------------------------------
  **Source**                        **How to test**

  Ruby                              rake test

  Node                              npm test

  Clojure                           lien test

  Python                            python -m unittest (this will depend)

  Java                              mvn test

  Java (again)                      gradlew test

  PHP                               Could be many options

  Go                                go test

  C#, .NET Core, .NET               Depends, usually dotnet test
  --------------------------------- -------------------------------------

### 

21. Tests are normally included as part of your other code in your
    project.

22. Testing can be a positive ROI activity, because they catch bugs
    before they enter production.

23. When we say "we don't test", what is usually meant is that testing
    isn't formalized. I don't think it is useful to say that startups
    shouldn't be writing tests, rather, it's important to look at how
    the overall testing strategy is employed with everything else.
    Startups usually don't have lots of guardrails, given the diversity
    of requirements and rapid change. A startup would prioritize
    software quality to some extent, for example, there is no purpose to
    continually write features if production is down and nobody can use
    your product. Someone, somewhere, or something has to evaluate it,
    whether it's customers, employees, monitoring, someone clicking on
    the website occasionally, etc. There might be customer reports, the
    CEO tries it out, etc. If nobody cares that the software is
    completely broken, then you have other issues with your business.

    1.  Testing is designed to prevent change. If something works, and
        all of a sudden it's different, then sound an alarm! In a way,
        this is good. My website has a shopping cart in the corner, and
        all of a sudden I can't find it. That's not good, and that's a
        form of change. Too much change is bad if you do not want too
        much change. If you want lots of change, then it's not helpful.

    2.  Testing slows down new work, but reduces overall effort to fix
        existing work. It makes changes more predictable as they are
        less likely to cause unintended changes, which smooths out the
        delivery lifecycle. This is only if your testing strategy is
        good. If you write lots of unit tests, for example, then this
        could impact the ability to refactor and could slow down both
        new work and existing work.

    3.  In an extreme approach, automated tests are just used once and
        rewritten. Therefore, they don't have much value, if any, as
        they were never run. They could be useful during development,
        although manually verifying the functionality might be
        straightforward.

    4.  Usually, what startups are aiming for is rapid change, so
        testing might drag down development velocity because there is
        so, so much change.

    5.  In more mature applications, there isn't usually that super high
        level of change. There are lots of small changes, but those can
        be accompanied by changing a few tests at a time. In startups,
        there is nothing to something, and testing something that isn't
        known yet is difficult.

    6.  You could argue that this form of testing (e.g., loading the
        website in your browser and clicking on some links) could be
        automated. And that is true. But the amount of testing that you
        get by just looking at it and just using the website is
        enormous, even if it doesn't feel like you're doing much.
        Automated testing is very streamlined and only demonstrates what
        has been proven. People have tacit knowledge and know when
        something is wrong, even if it cannot be formalized in computer
        code. Say there's a header that is a bit too small, the colors
        aren't quite right, or something flickers. These could, in
        theory, be part of the automated test suite, but there has to be
        an observation first for the computer to know that this is
        wrong. Automated tests are usually small in scope as well.

```{=html}
<!-- -->
```
4.  ### How to write a test and types of tests

    1.  #### Testing frameworks

        1.  What are some testing tools that are available? JUnit,
            Selenium, Jest are testing frameworks that allow you to
            better structure your tests. They can also integrate with
            the CI/CD pipeline and can generate a report (which is in a
            format suitable for the CI/CD pipeline to consume) which can
            show you different statistics, such as code coverage, which
            tests failed, how long the tests took to run, which tests
            were disabled/enabled, etc. These reports can be aggregated
            and used to find out which tests normally fail, allowing the
            developers to prioritize which tests are the most important.
            They can also help you write tests, by providing common
            methods or functions that can be used to setup test
            environments, and check for equality to reference data.
            These allow for other developers on your team to collaborate
            on a common framework and can increase understanding, as the
            test frameworks are usually very popular and many developers
            have had experience with them. They can also automate much
            of the "grunt-work", such as the internals of UI testing.

    2.  #### Unit testing

        1.  *Unit tests are a type of software testing where individual
            units or components of a software application are tested in
            isolation from the rest of the code. The purpose of unit
            testing is to validate that each unit of the software
            performs as designed. A \"unit\" is the smallest testable
            part of an application and can be as small as a single
            function or method within a class.*

        2.  

3.  Unit tests are good for testing components that are being worked on
    during the development period, and can be run very quickly in a
    developer's workflow. They are designed for testing a single unit,
    which could be a single function or a few functions together. These
    are likely fragile tests, as they check implementation details. This
    doesn't mean that you shouldn't write them, rather, it depends on
    what application you are making and what your test strategy is.

4.  Unit testing in and of itself should not be the goal, unless you're
    working on safety critical systems (in which case regulations may
    vary.)

5.  Unit tests are useful, for example, when the response may not exist.
    For example, testing a weather app and you want to know if your app
    can display if it is sunny. However, the weather may not be sunny,
    and it isn't possible to access historical data. Here, it makes
    sense to mock the response.

6.  Think of a car motor analogy, you can test all of the parts
    individually on your desk, but it's meaningless if they are not put
    together and run. However, testing each part individually can yield
    insights that would not be possible by testing the system as whole,
    namely issues that could occur in the future, or potential failure
    scenarios that would be difficult to create when everything is put
    together. The system should fail cleanly if there is an issue with a
    single part, but might be difficult to test when it is all put
    together.

7.  Unit testing has the ability to test theoretical inputs and outputs,
    in addition to practical concerns.

8.  Unit tests are better when testing a single component in isolation
    or if there is a situation that is an edge case or is difficult to
    reproduce through the UI. For example, if an item is out of stock,
    then the UI might not allow adding it to the cart, but a unit test
    can verify that it actually cannot be added. If you have to "reach
    through" the UI to do testing, then it might mean that you are
    testing too high-level. If you have to "reach up" and have to
    connect multiple components together, then you might benefit from
    component testing (or a higher-level testing approach.)

9.  Unit tests are also good for ensuring that internal state and
    outputs to APIs are ok. This makes them partially suited for the
    back-end, because each step of the operation may require special
    handling. It might not be clear from an E2E test if data was
    intermittently calculated correctly. For example, consider an
    application that detects if there is fraud. The input is the
    variables and the output is a probabilistic estimate. One can
    determine if the inputs are the same as the output (effectively
    treating it as a blackbox), however, if it is an ensemble and there
    is one provider that is not responding, then this would be a cause
    for concern, something that an E2E test could not catch.

10. Unit tests useful for verifying integrations with other software,
    which may or may not have intimate knowledge about what your
    function accepts. They are also useful when integrating with other
    systems (e.g., to preserve backwards compatibility.)

11. Unit tests can help identify a particular component that is not
    operating correctly or to an expectation. Therefore, they are useful
    proactive debugging tools. It might be difficult to narrow down the
    cause with an E2E test or a component test as it takes the entire
    system as black box and then evaluates its inputs and outputs, as if
    a customer was using it.

12. Unit testing can be helpful in situations where you need to mock
    something. For example, consider an application that wraps a
    database in a cache. In order to test the function, an E2E test
    could be used, but this neglects testing the cache, it tests
    everything. A function without the cache would return the same
    result. Therefore, you can use a unit test to check if the cache is
    being used because you can inspect and modify the internal state.

```{=html}
<!-- -->
```
3.  #### Integration Testing

    1.  "Integration tests are a type of software testing where
        individual units or components of a software are combined and
        tested as a group. The primary purpose is to validate the
        interactions between the different parts of a system, such as
        modules, functions, or services. While unit tests focus on
        ensuring that individual parts of the system work as expected in
        isolation, integration tests aim to uncover issues that may
        arise when these parts are combined." ChatGPT

    2.  

+-----------------------------------------------------------------------+
| Certainly! Integration tests differ from unit tests in that they      |
| usually test the interactions between multiple components or layers   |
| of an application, such as the communication between a service and a  |
| database, or between different services.                              |
|                                                                       |
| For this example, let\'s consider an integration test for a service   |
| that interacts with a database. We\'ll use Entity Framework Core (EF  |
| Core) to illustrate this.                                             |
|                                                                       |
| 1\. First, let\'s define a simple entity and a context for EF Core:   |
|                                                                       |
| \`\`\`csharp                                                          |
|                                                                       |
| public class User                                                     |
|                                                                       |
| {                                                                     |
|                                                                       |
| public int Id { get; set; }                                           |
|                                                                       |
| public string Name { get; set; }                                      |
|                                                                       |
| }                                                                     |
|                                                                       |
| public class AppDbContext : DbContext                                 |
|                                                                       |
| {                                                                     |
|                                                                       |
| public AppDbContext(DbContextOptions\<AppDbContext\> options) :       |
| base(options)                                                         |
|                                                                       |
| {                                                                     |
|                                                                       |
| }                                                                     |
|                                                                       |
| public DbSet\<User\> Users { get; set; }                              |
|                                                                       |
| }                                                                     |
|                                                                       |
| \`\`\`                                                                |
|                                                                       |
| 2\. Create a service that uses this context:                          |
|                                                                       |
| \`\`\`csharp                                                          |
|                                                                       |
| public class UserService                                              |
|                                                                       |
| {                                                                     |
|                                                                       |
| private readonly AppDbContext \_context;                              |
|                                                                       |
| public UserService(AppDbContext context)                              |
|                                                                       |
| {                                                                     |
|                                                                       |
| \_context = context;                                                  |
|                                                                       |
| }                                                                     |
|                                                                       |
| public User GetUser(int id)                                           |
|                                                                       |
| {                                                                     |
|                                                                       |
| return \_context.Users.Find(id);                                      |
|                                                                       |
| }                                                                     |
|                                                                       |
| }                                                                     |
|                                                                       |
| \`\`\`                                                                |
|                                                                       |
| 3\. Now, let\'s write an integration test for the \`GetUser\` method  |
| using MSTest and the \`Microsoft.EntityFrameworkCore.InMemory\`       |
| package (an in-memory database provider for EF Core):                 |
|                                                                       |
| \`\`\`csharp                                                          |
|                                                                       |
| using Microsoft.EntityFrameworkCore;                                  |
|                                                                       |
| using Microsoft.VisualStudio.TestTools.UnitTesting;                   |
|                                                                       |
| \[TestClass\]                                                         |
|                                                                       |
| public class UserServiceTests                                         |
|                                                                       |
| {                                                                     |
|                                                                       |
| private AppDbContext \_context;                                       |
|                                                                       |
| private UserService \_service;                                        |
|                                                                       |
| \[TestInitialize\]                                                    |
|                                                                       |
| public void TestInitialize()                                          |
|                                                                       |
| {                                                                     |
|                                                                       |
| // Set up the in-memory database.                                     |
|                                                                       |
| var options = new DbContextOptionsBuilder\<AppDbContext\>()           |
|                                                                       |
| .UseInMemoryDatabase(databaseName: \"TestDatabase\") // Unique name   |
| for the in-memory database.                                           |
|                                                                       |
| .Options;                                                             |
|                                                                       |
| \_context = new AppDbContext(options);                                |
|                                                                       |
| \_service = new UserService(\_context);                               |
|                                                                       |
| // Add sample data.                                                   |
|                                                                       |
| \_context.Users.Add(new User { Id = 1, Name = \"Alice\" });           |
|                                                                       |
| \_context.SaveChanges();                                              |
|                                                                       |
| }                                                                     |
|                                                                       |
| \[TestMethod\]                                                        |
|                                                                       |
| public void GetUser_ValidId_ReturnsUser()                             |
|                                                                       |
| {                                                                     |
|                                                                       |
| // Act                                                                |
|                                                                       |
| var user = \_service.GetUser(1);                                      |
|                                                                       |
| // Assert                                                             |
|                                                                       |
| Assert.IsNotNull(user);                                               |
|                                                                       |
| Assert.AreEqual(\"Alice\", user.Name);                                |
|                                                                       |
| }                                                                     |
|                                                                       |
| \[TestCleanup\]                                                       |
|                                                                       |
| public void TestCleanup()                                             |
|                                                                       |
| {                                                                     |
|                                                                       |
| // Clean up resources, e.g., dispose the context, etc.                |
|                                                                       |
| \_context.Database.EnsureDeleted();                                   |
|                                                                       |
| \_context.Dispose();                                                  |
|                                                                       |
| }                                                                     |
|                                                                       |
| }                                                                     |
|                                                                       |
| \`\`\`                                                                |
|                                                                       |
| Here\'s what happens in the integration test:                         |
|                                                                       |
| \- \`\[TestInitialize\]\`: This method runs before each test. We\'re  |
| setting up an in-memory database, adding a sample user, and           |
| initializing the \`UserService\`.                                     |
|                                                                       |
| \- \`GetUser_ValidId_ReturnsUser\`: This test method checks whether   |
| the \`GetUser\` method retrieves the correct user from the database.  |
|                                                                       |
| \- \`\[TestCleanup\]\`: This method runs after each test. We\'re      |
| ensuring the in-memory database is deleted and disposing the context. |
|                                                                       |
| By using an in-memory database for integration testing, we simulate   |
| interactions with a real database without the overhead of actual      |
| database operations.                                                  |
+-----------------------------------------------------------------------+

3.  

```{=html}
<!-- -->
```
4.  #### Regression Testing

    1.  "Regression testing is a type of software testing that aims to
        ensure that new code changes do not adversely affect the
        existing functionalities of a system. The primary objective is
        to catch bugs that may have been introduced into previously
        working code, or to ensure that recent changes or additions
        haven\'t broken any existing features." - ChatGPT

    2.  If my application has a bug, and then I fix it, and then that
        bug appears again, then I should write a regression test to make
        sure that that bug doesn't happen again (i.e., a regression.)

    3.  This is more of a concept, because it's just a regular test that
        has been created to fix a previously existing bug.

5.  #### Performance and Load Testing

    1.  Useful to make sure that the application can still meet
        performance requirements of users.

    2.  This is important because changes to the source code (and new
        features) can impact the performance in small but subtle ways.
        The application can *still work, per-se* but it might not
        operate quickly. Tests normally have a timeout of about 30s to a
        minute, sometimes with no timeout (requires human intervention.)
        This means that all of the other tests can still pass, as they
        normally don't have criteria on how much time has elapsed. Also,
        performance and load testing tests deliberately create many
        thousands or hundreds of thousands of requests, and may also
        offer profiling tools and more precise measures of request
        timings that are not necessary for regular unit tests.

6.  #### End-to-End (E2E) Testing

    1.  Useful to make sure that the entire application functions as a
        whole. When I click on a button, then I see an output for
        example, big picture tests.

    2.  For example, I want to click on a button and then see something
        happen. I don't care how the implementation works, I just care
        about the output or the outcome.

    3.  Or, I'm making an HTTP request to a server and I want to see
        what the result is. I don't care what programming language it is
        written in or its implementation, I'm just checking its output.

    4.  These are usually very customer- or user-oriented tests because
        they might operate on the UI that the customer sees.

7.  #### non-functional testing/user testing/security testing

    1.  Non-functional testing is the ability to test things that don't
        have a defined result that can be clearly articulated, it's "you
        know it when you see it." For example, one is able to view a
        piece of art and know that it looks nice but they might not be
        able to create new art that looks nice as they do not know the
        criteria.

    2.  This might also include user testing, which is also tacit
        knowledge. For example, the layout of the application is too
        confusing and difficult for users to navigate. Here, automated
        tests wouldn't be able to identify this, because they merely
        follow instructions that they were programmed to do, and don't
        have a concept as to whether something is intuitive for a user
        to use.

5.  ### Best Practices and Challenges in Software Testing

    1.  Importance of avoiding overlaps and ensuring broad test
        coverage. This requires that the tests are well organized and
        understood to prevent testing duplicate functionality, although,
        it is likely that there will be some overlap in tests (e.g.,
        setup.) By having the tests organized, it also helps with
        ensuring that there is sufficient test coverage (in terms of
        functionality) because you know which things are and are not
        tested.

    2.  When you're writing tests, chances are that there will be a lot.
        Therefore, make sure that you know how to selectively run a
        certain test or a suite of tests that are likely to be impacted
        by what you are changing. This will greatly improve the feedback
        loop. In some frameworks, the test agent can be run in the
        background and automatically determine which test(s) to run
        based on what code you've changed. In your CI pipeline, you may
        want to either selectively run tests based on what has changed,
        or run all tests.

    3.  In order to organize the tests well, make sure that you have a
        good naming convention, and, if applicable, store the tests next
        to the modules that they are testing. There are lots of
        exceptions, and each programming language might have best
        practices on how to store and manage test cases.

    4.  

+-----------------------------------------------------------------------+
| The \"top 5 programming languages\" can vary depending on the context |
| and metric being used, such as popularity, job demand, or             |
| performance. However, as of my last training cut-off in January 2022, |
| the TIOBE Index, RedMonk Rankings, Stack Overflow Developer Survey,   |
| and other sources often listed languages like Java, Python,           |
| JavaScript, C#, and C (or C++) among the top ranks.                   |
|                                                                       |
| Here\'s a brief overview of how testing is structured on disk for     |
| these languages:                                                      |
|                                                                       |
| 1\. \*\*Java\*\*:                                                     |
|                                                                       |
| \- Framework: JUnit (most popular)                                    |
|                                                                       |
| \- Test Structure: Java tests are typically placed in a separate      |
| \`test\` directory that mirrors the structure of the \`src\`          |
| directory. For example:                                               |
|                                                                       |
| \`\`\`                                                                |
|                                                                       |
| project-root/                                                         |
|                                                                       |
| ├── src/                                                              |
|                                                                       |
| │ ├── main/                                                           |
|                                                                       |
| │ │ ├── java/                                                         |
|                                                                       |
| │ │ │ └── com/example/MyClass.java                                    |
|                                                                       |
| │ ├── test/                                                           |
|                                                                       |
| │ │ ├── java/                                                         |
|                                                                       |
| │ │ │ └── com/example/MyClassTest.java                                |
|                                                                       |
| \`\`\`                                                                |
|                                                                       |
| 2\. \*\*Python\*\*:                                                   |
|                                                                       |
| \- Framework: pytest, unittest                                        |
|                                                                       |
| \- Test Structure: Python tests can be placed alongside the source    |
| code or in a separate \`tests\` directory. Some projects use a        |
| \`test\_\*.py\` naming convention for test modules.                   |
|                                                                       |
| \`\`\`                                                                |
|                                                                       |
| project-root/                                                         |
|                                                                       |
| ├── my_module.py                                                      |
|                                                                       |
| ├── test_my_module.py                                                 |
|                                                                       |
| \`\`\`                                                                |
|                                                                       |
| Or:                                                                   |
|                                                                       |
| \`\`\`                                                                |
|                                                                       |
| project-root/                                                         |
|                                                                       |
| ├── src/                                                              |
|                                                                       |
| │ ├── my_module.py                                                    |
|                                                                       |
| ├── tests/                                                            |
|                                                                       |
| │ ├── test_my_module.py                                               |
|                                                                       |
| \`\`\`                                                                |
|                                                                       |
| 3\. \*\*JavaScript\*\*:                                               |
|                                                                       |
| \- Framework: Jest, Mocha, Jasmine                                    |
|                                                                       |
| \- Test Structure: For many JavaScript projects, especially those     |
| using Node.js, tests are often in a \`\_\_tests\_\_\` directory or    |
| alongside the source code with a \`.test.js\` or \`.spec.js\` suffix. |
|                                                                       |
| \`\`\`                                                                |
|                                                                       |
| project-root/                                                         |
|                                                                       |
| ├── src/                                                              |
|                                                                       |
| │ ├── myFunction.js                                                   |
|                                                                       |
| │ ├── myFunction.test.js                                              |
|                                                                       |
| \`\`\`                                                                |
|                                                                       |
| 4\. \*\*C#\*\*:                                                       |
|                                                                       |
| \- Framework: MSTest, NUnit, xUnit                                    |
|                                                                       |
| \- Test Structure: C# tests are typically placed in a separate test   |
| project, which might be in the same solution. For example:            |
|                                                                       |
| \`\`\`                                                                |
|                                                                       |
| solution-root/                                                        |
|                                                                       |
| ├── MyProject/                                                        |
|                                                                       |
| │ ├── MyClass.cs                                                      |
|                                                                       |
| ├── MyProject.Tests/                                                  |
|                                                                       |
| │ ├── MyClassTests.cs                                                 |
|                                                                       |
| \`\`\`                                                                |
|                                                                       |
| 5\. \*\*C/C++\*\*:                                                    |
|                                                                       |
| \- Framework: Google Test, Catch2                                     |
|                                                                       |
| \- Test Structure: Tests in C++ are typically separated into their    |
| own files, which might be placed in a \`test\` or \`tests\`           |
| directory.                                                            |
|                                                                       |
| \`\`\`                                                                |
|                                                                       |
| project-root/                                                         |
|                                                                       |
| ├── src/                                                              |
|                                                                       |
| │ ├── my_function.cpp                                                 |
|                                                                       |
| │ ├── my_function.h                                                   |
|                                                                       |
| ├── tests/                                                            |
|                                                                       |
| │ ├── test_my_function.cpp                                            |
|                                                                       |
| \`\`\`                                                                |
|                                                                       |
| It\'s worth noting that the structure of tests can vary depending on  |
| the project\'s conventions, the testing framework, or the             |
| developer\'s personal preferences. The examples provided are common   |
| conventions but are by no means strict rules.                         |
+-----------------------------------------------------------------------+

5.  

6.  Understanding code coverage and mutation testing. Code coverage is
    somewhat useful but has many limitations and it is important that
    one knows what it can and cannot do. Code coverage is a metric that
    shows if there is a test that covers (i.e., runs) that part of the
    function or code, and then it is averaged out among all of the
    methods or statements in the project. It cannot test whether the
    tests are useful or make sense, it only checks if the code is
    executed. This is akin to a very large paintbrush; if there is zero
    percent code coverage, then the module isn't tested. If it's
    anywhere from not zero to 100%, then the module is tested. Aiming
    for 100% code coverage, for most applications, might be unnecessary
    because it does not encourage a useful high-level test strategy and
    can cause developers to write useless or less useful tests, purely
    to make the number get to 100%. Some items in the project aren't
    worth being tested, and writing too many tests can make refactoring
    very difficult. [[testing - What is code coverage and how do YOU
    measure it? - Stack
    Overflow]{.underline}](https://stackoverflow.com/questions/195008/what-is-code-coverage-and-how-do-you-measure-it?rq=3)

7.  If you have 90% code coverage, it is unclear what the 10% uncovered
    code does. Was it just difficult to test, or was it worthwhile to
    test?

8.  How do you analyze and interpret test results to identify issues and
    prioritize fixes?

    1.  ![A screenshot of a test results Description automatically
        generated](vertopal_7cf17b12d305426e8597d711f8f376f6/media/image4.png){width="6.114583333333333in"
        height="2.84375in"}

    2.  ![A screenshot of a test Description automatically
        generated](vertopal_7cf17b12d305426e8597d711f8f376f6/media/image5.png){width="6.40625in"
        height="3.3125in"}

    3.  [[Publish Test Results · Actions · GitHub
        Marketplace]{.underline}](https://github.com/marketplace/actions/publish-test-results).
        Test results are sent to a global database where a report can
        run and you can view all of the results together.

9.  When should the tests run? Should they be run on the PR, after it is
    merged, pre-deployment, or post-deployment?

    1.  Running tests on the PR allows for catching bugs before they
        impact other developers or break the central pipeline. Usually,
        when phrases such as "keeping the pipeline green" are used, they
        mean to keep the deployment pipeline green (and the post-merge
        pipeline) as if these are not working, then it is not possible
        to generate a release. Sometimes, your PR run (on a PR pipeline)
        might fail. This doesn't impact other developers, but it is
        still vital that it is fixed because otherwise you won't be able
        to merge.

    2.  Some tests have hard requirements. For example, if you want to
        test the entire application deployed, then it will have to be a
        post-deployment test. Post-deployment tests are useful when you
        want to test the entire application's functionality. The only
        way to truly know if your application is running as intended.

10. How do you manage test results and test cases over time?

    1.  After the tests have concluded on the CI runner (usually
        post-merge, pre-deployment, or post-deployment), the results can
        be published to a test server, where they are aggregated. This
        is usually vendor-specific.

    2.  Normally, test results from a single PR are available on the PR
        itself, but might not be available on the central test
        repository dashboard. This is because PRs are still, in theory,
        a work in progress and don't represent the entirety of the
        application. Therefore, once a PR is merged, it is temporary and
        has been erased. If one tries to calculate or aggregate the test
        coverage from all of the PRs, it might be difficult to determine
        what the true test coverage for the application is. Therefore,
        normally, the test coverage of the application is derived from a
        post-merge task/build task.

    3.  You can normally publish the test results when setting up a
        pipeline. Many testing frameworks automatically allow generating
        test artifact/run data in a format suitable for consumption by a
        computer, usually in JSON or XML.

    4.  Some testing dashboards can show which tests commonly fail, how
        long the tests took to run, and which tests are flaky. This can
        help prioritize where to add more tests and to find areas of
        your application that need special attention.

    5.  Note: because an area has more failing tests does not mean that
        it is intrinsically more fallible. This is because someone could
        not write tests for a component, and therefore no tests would
        fail--this does not mean that the component is safer or better
        written. It also doesn't mean that the tests are written well;
        flaky tests or useless tests may fail or pass respectively and
        fail to provide useful information.

11. Spend a bit more on testing environments if they're slow. It's a
    useful tool, so invest in it. The increased ROI by CI/CD (i.e., the
    more profit generated by creating more features) should
    significantly outweigh any additional testing costs.

12. Why do we need to run tests on the CI, and developers machines?

+-----------------------------------------------------------------------+
| Key Points:                                                           |
| [[https://softwareengineering.stackexchange.com/a/308517/22753]{.unde |
| rline}](https://softwareengineering.stackexchange.com/a/308517/22753) |
|                                                                       |
| 1\. Developers may not always run all unit tests before committing to |
| master due to:                                                        |
|                                                                       |
| a\. Lack of discipline.                                               |
|                                                                       |
| b\. Forgetfulness.                                                    |
|                                                                       |
| c\. Incomplete commit sets.                                           |
|                                                                       |
| d\. Running only a selection of tests.                                |
|                                                                       |
| e\. Testing on their branch before merging.                           |
|                                                                       |
| 2\. It\'s essential to run tests on a machine different from the      |
| developer\'s to:                                                      |
|                                                                       |
| a\. Identify issues relying on specific configurations, data,         |
| timezone, locale, etc., unique to the developer\'s machine.           |
|                                                                       |
| 3\. CI (Continuous Integration) builds offer multiple benefits:       |
|                                                                       |
| a\. Tests can be run on platforms other than the primary development  |
| platforms.                                                            |
|                                                                       |
| b\. Acceptance, Integration, End-to-End, and long-running tests are   |
| often conducted on the CI server.                                     |
|                                                                       |
| c\. CI servers can detect overlooked minor changes made by developers |
| who assume such changes are safe.                                     |
|                                                                       |
| d\. CI servers\' configuration is usually free of developer-specific  |
| tools, making it more akin to the production system.                  |
|                                                                       |
| e\. CI systems ensure repeatable builds by constructing the project   |
| from scratch every time.                                              |
|                                                                       |
| f\. In the event of a library modification, CI servers can be set up  |
| to build all dependent codebases to pinpoint potential downstream     |
| issues.                                                               |
+-----------------------------------------------------------------------+

1.  On the CI runner, tests are normally run on the pull request and
    blocks the pull request from being merged if the tests fail. Tests
    may also run at other points, such as after the PR is merged, prior
    to deployment, and after deployment.

```{=html}
<!-- -->
```
13. When are mocks useful?

    1.  Testing a shopping cart to ensure that it can handle multiple
        items and provide the correct total price, even when one of the
        items is out of stock.

    2.  Testing a login page to ensure that it handles invalid passwords
        correctly and provides the correct error message.

    3.  Testing a search function to ensure that it returns results that
        match the search criteria, even if the actual search engine
        returns no results.

    4.  Testing an e-commerce site to ensure that it can handle high
        traffic during holiday shopping seasons.

    5.  Testing a payment gateway to ensure that it processes
        transactions correctly, even when the bank\'s system is down for
        maintenance.

14. In the end, if you absolutely cannot make the tests any shorter, try
    to understand what value the tests are providing to the business.
    Consider only running a selection of tests, and some others less
    often. Can the customers not tolerate faulty software, and require
    extensive testing procedures? Reference the triangle of quality,
    speed, and cost. You may want to get a better understanding of what
    your customers really want, and could consider customer
    segmentation. For example, providing a beta version of your software
    that is not as tested but to outsource the priorities of the testing
    to the customers. Or, to allow customers to get the software sooner
    but it might not be as well tested, while also providing a more
    stable version for those who want a more tested software.

15. \*\*Testing Philosophy & Prioritization:\*\*

    1.  Ultimately, the user sees what is displayed on the screen, i.e.,
        an end-to-end test. However, it might not be feasible to always
        write end-to-end tests, because they might be slow to run (which
        might be difficult to improve if your application is complex),
        and if there is a failure in a lower layer, it might be
        ambiguous as to if the UI or the lower layer is responsible for
        the bug, i.e., tests can be used as debugging tools. Normally,
        end-to-end tests do not run at the same frequency as your unit
        tests, and so the feedback loop is a bit slower. This will
        depend on your company, and is usually a reactive approach: as
        you find bugs that are found in your E2E tests, then you have to
        track them against which commit fixed that bug, therefore, small
        commits are good to have to be able to associate them together.
        Once you find the root cause of the bug, then you can determine,
        over time, in general, if the tests are too high level or too
        low level.



2.  In some cases, it depends on what you are trying to test. For
    example, if I am doing an end-to-end test to add an item to my
    shopping cart, and I am trying to figure out if accounting receives
    the electronic paperwork, then since this is not exposed to the
    customer, I can't write an end-to-end test for this, unless I inject
    myself into private methods. It depends a bit on the testing
    scenario as well; if you want to do a complex purchase order and
    also see whether accounting gets the paperwork, then an end to end
    test might be useful.

3.  Recall that tests are useful debugging tools as well, as they show
    which assumption was violated. Therefore, say you have three
    functions, A, B, and C. They all produce an output, and are summed
    together via D. I could write a test for D, but if A, B, or C fails
    then I won't know which one failed, only that the output from D is
    wrong. So, I'd have to look into all four functions to find the root
    cause of the bug. In this case, you could have written a unit test
    for A, B, or C and then have been able to find the issue.

4.  Consider a real-world scenario where you\'re developing a financial
    application that helps users visualize their potential savings
    growth using a monte-carlo simulation. The application integrates
    with third-party banking APIs to fetch the user\'s financial
    transactions over the past year. Users simply connect their bank
    accounts, press "Run," and a report is generated to display
    projected savings based on their historical data.

5.  Now, here\'s the challenge:

    1.  Variability in Results: Each time the report is run, the
        monte-carlo simulation provides slightly different results due
        to its inherent probabilistic nature.

    2.  Opaque Data: While users see a summarized report, the finer
        details fetched from the bank via the API---details crucial for
        the computation---are not accessible through the UI. Scraping
        this data from the UI is not only complicated but also prone to
        errors.

6.  Given these conditions, how can you ensure, with confidence, that
    the monte-carlo calculations are accurate? Relying on high-level E2E
    tests would mean:

    1.  Using a Threshold: You\'d need to set a threshold to account for
        the variability in the monte-carlo results. But what should this
        threshold be? Setting it too broad might overlook significant
        computational errors, while setting it too narrow could trigger
        false negatives.

    2.  Dependence on External Data: E2E tests would rely on the data
        from third-party APIs, meaning any change or unavailability on
        their part could disrupt your testing.

7.  Contrast this with the clarity and control offered by unit testing:

    1.  Consistent Results: By mocking methods, like the random number
        generation used in the monte-carlo simulation, you can use seeds
        to ensure consistent results across runs. This allows you to
        precisely verify calculations without the variability introduced
        by true randomness.

    2.  Focused Testing: Unit tests would isolate and test just the
        computational logic, removing dependencies on the UI or
        third-party APIs. This way, you can simulate various financial
        scenarios and verify the accuracy of the monte-carlo logic
        independently.

8.  In conclusion, this is why it is important to develop a good testing
    strategy: what I am trying to measure is the result of the
    computation, and whether the computations are accurate. It is
    possible that those computations might not be displayed correctly on
    the UI, thus, it might be useful to have an E2E test too.

9.  A case where a unit test would be useful is to verify if a caching
    layer for a database works. If the caching layer does not exist,
    then it still returns the same data, thus, there isn't a failure
    case necessarily. TDD is very useful in this scenario (how would you
    know if the caching layer failed?) This might help you to figure out
    which layer to write your test on.

    1.  In very over-simplified terms: if you need more control and
        there is uncontrollable factors (such as third-party
        integrations, different data, etc.) use unit tests, if you find
        yourself re-creating the entire environment or you want to see
        what the customer sees, trying to capture multi-page navigation,
        animations, network failures, buttons/ui elements, click
        handlers, whether the database displays the correct results to
        the user, use E2E tests.

10. Say if you are writing a calendar application that allows you to
    schedule appointments with other people. The application provides
    the ability to schedule an appointment with someone else in the
    future, by checking their schedule and your schedule. Then, the list
    of potential dates that work for both people are shown in the UI,
    but only the top 10 are shown. You want to be able to find out all
    of the dates that the two people can be scheduled together. In this
    case, a unit test might make more sense, because it might be complex
    to parse the information from the UI (say that it is in multiple
    cultures), and you want to have more information than what is listed
    on the UI. This might also make it less brittle from a test
    perspective because any changes to the UI (say that it is undergoing
    a redesign with some new icons and colors), then the unit tests are
    less likely to be impacted.

11. Understand the balance between quality, speed, and cost.

12. Consider what the business wants and the acceptable quality of
    software. Testing too much or too little is inefficient. Testing the
    wrong things is also inefficient.

13. Consider timeboxing the testing. Prioritize tests and get as much
    done within a set timeframe.

14. Use real user metrics to evaluate frequently used parts of the
    application. Prioritize testing for these sections.

15. It may be necessary to compromise on quality if efficiency cannot be
    improved.

16. Sometimes, reduce emphasis on quality temporarily to gather customer
    feedback.

17. If customers are indifferent to test results, evaluate your customer
    base and potential quality issues.

18. If tests are deemed slow, understand what they\'re slow relative to.
    Consider potential trade-offs for keeping these tests.

```{=html}
<!-- -->
```
16. \*\*Operational Strategies:\*\*

    1.  Create multiple test accounts or run parallel tests across
        multiple environments to address slow tests.

    2.  If unsure about bug prioritization, release the software and
        gather bug reports.

    3.  Consider a beta program where users actively search for bugs.

    4.  QA testing should not impede developers. The testing process
        should be swift, and mainly require human insights.

    5.  Identifying areas that could be automated, or areas that should
        not be automated, and the role of the QA tester (if there is
        one). For example, testing plans consist (usually) of a set of
        instructions that testers are to follow and also contain
        expected outputs. If the tests are not open to interpretation,
        then it might mean that they are candidates for automation.
        Having these test plans as part of the test repository allows
        for a streamlined and holistic view of all of the testing and
        its statuses.

    6.  Monitoring how many test cases exist, and how many are disabled.

    7.  Consider outsourcing if the app\'s complexity impedes the QA
        process.

    8.  Integrate testers with developers early on. Encourage mutual
        responsibilities in testing to share the workload.

    9.  Explore architectural reviews if frequent bugs emerge.

    10. Think about implementing CI/CD and weigh its benefits. It can
        expedite software delivery but may require quality compromises.

    11. Ensure easy reversion processes. If a production bug arises,
        reverting should be quick.

17. \*\*Test Building & Management:\*\*

    1.  How does one construct maintainable tests?

    2.  For tracking test failures, correlate tests to source files.

    3.  Focus on abstraction levels and automation patterns.

    4.  Create declarative tests with clear dependencies.

    5.  Test popular third-party browser extensions.

    6.  Understand test impact analysis.

    7.  Consider the goals and purposes of the tests. Define parameters
        clearly.

    8.  Investigate equivalence theory. Understand relaxed equivalence
        specifications.

    9.  Committing should include both excluded and focused tests.

    10. Hash functions can serve as approximate equality functions.

    11. Creating tests should be as carefully considered as deleting
        them.

18. \*\*Bug Evaluation & Addressing:\*\*

    1.  Determine types of bugs found in production
        (requirements-oriented, automatable, usability).

    2.  Assess the impact of bugs in production. Implement solutions
        based on their severity.

    3.  Re-evaluate overly detailed requirements. Too much detail can
        cloud the overall objective.

    4.  Consider shorter development cycles or Agile methodologies to
        address severe production bugs.

19. \*\*Customer-Centric Testing:\*\*

    1.  Understand customer needs. Evaluate the balance between quality,
        feature quantity, and release speed.

    2.  Offer different versions: a less-tested, fast-release version
        and a more stable, thoroughly-tested version.

    3.  Gauge what customers truly prioritize. Is it a faster release,
        more features, or higher quality?

    4.  Understand the testing pyramid. Adapt tests according to the
        application\'s needs. For instance, E2E UI API tests might be
        unnecessary if an API is used by another system only.

    5.  Stopping writing tests because they're slow or because they're
        flaky means that these are addressing the symptoms, not the root
        causes. If they're slow, then this is relative to something
        else. Are they important to be run? Does that mean that all
        future tests are by default of lesser priority than everything
        thus far?

20. \*\*Race Conditions and Asynchronous Processing:\*\*

    1.  Ensure the cleanliness of the shared state.

    2.  Utilize callbacks for asynchronous processes.

    3.  Use polling for updated values, timing out after a specified
        interval if dependent on another service.

    4.  Employ library functions to make temporary folders and files.

    5.  Use transactions, where possible, for database interactions.

21. \*\*Fuzzing:\*\*

    1.  Ensure code can manage both minimum and maximum values within a
        range.

    2.  Be cautious with invalid UTF-8 characters in random strings.

    3.  Understand the probability of flaky tests.

    4.  You should probably run the test many times if this is the first
        time committing it, so that you can proactively avoid committing
        flaky tests.

    5.  Post-deployment testing is useful because there is a possibility
        that your PPE environments are not aligned with production.
        Production is what users will see, so it doesn't matter how
        fancy your PPE env is, Prod is what matters. Definitely do
        triage it immediately, and if it should not be fixed, then it
        should be disabled. It depends on the level of trust in the team
        and if people are self-sufficient and can prioritize correctly,
        or, if they should handle it immediately because the probability
        of deferring a test would be too risky. If one had to
        immediately fix all flaky tests, irregardless of priority, then
        this would eventually force only writing high-priority tests,
        which may not align with the test strategy, or, it might mean
        that future tests are not written because that could increase
        the number of tests, thus, the probability of flaky tests
        increases. If you have 100000 tests, there's bound to be flaky
        ones that come up and if you're not careful, then you'll be
        fixing tests forever and not getting any work done.

    6.  If you have 100,000 or 10,000 tests and some are flaky, can you
        narrow it down to certain ones? You should keep track of test
        fail/pass rates and if they succeed when re-running them. If
        there is a single one that is flaky, it can be triaged. If there
        are many that are flaky, then it might be more difficult.

    7.  Also consider running the tests on single-threaded or
        multi-threaded CPUs, or slower CPUs, or ones with a stress-test
        running. This might help reveal flakyness (? #review# add in
        paper here that had those suggestions.)

22. \*\*Consistent Environment:\*\*

    1.  Determine whether you\'re checking the quantity or precision of
        received events.

    2.  Avoid tagging dependencies as \"latest.\"

    3.  Utilize \`package.lock.json\` for locking dependencies.

    4.  Clean up by deleting temporary files.

    5.  Consider environment dependencies and restrictions.

23. \*\*Tips and Best Practices:\*\*

    1.  Use DOM testing instead of snapshot testing for visual
        regressions.

    2.  Prioritize testing where it makes the most sense, without
        getting overly focused on the test pyramid.

    3.  Delete temporary files and ensure you have permission to write
        files.

    4.  Be wary of tagging dependencies as the latest version.

    5.  Employ Canary pipelines to test new versions of resources, like
        an Ubuntu image.

    6.  When defining equivalence relations, consider context,
        precision, alternative definitions, and potential drawbacks.

    7.  Be mindful of potential pitfalls with race conditions, like
        making sure ports aren\'t in use, or ensuring sockets and
        resources become available.

    8.  For fuzzing, be vigilant of HTTP settings for long-running calls
        and adhere to valid character sets.

    9.  Maintain a consistent environment, ensuring permissions,
        handling database buffers, and being aware of potential
        environmental dependencies.

    10. 

+-----------------------------------------------------------------------+
| [[Why-Most-Unit-Testing-is-Waste.pdf                                  |
| (rbcs-us.com)]{.underlin                                              |
| e}](https://rbcs-us.com/documents/Why-Most-Unit-Testing-is-Waste.pdf) |
|                                                                       |
| Certainly, the provided text offers a critical look at the practice   |
| of unit testing in software development. Here are the key points:     |
|                                                                       |
| \### Limitations of Unit Testing                                      |
|                                                                       |
| 1\. \*\*Overemphasis on Code Coverage\*\*: The text argues that code  |
| coverage is not a good metric for software quality, as it doesn\'t    |
| necessarily indicate that the code does what it\'s supposed to do.    |
|                                                                       |
| 2\. \*\*Duplication of Effort\*\*: It suggests that unit tests often  |
| duplicate what system tests and integration tests are designed to do. |
|                                                                       |
| 3\. \*\*Green Bar Fever\*\*: The text warns against a narrow focus on |
| making tests pass (the \"Green Bar\") at the expense of a more        |
| comprehensive understanding of the system.                            |
|                                                                       |
| 4\. \*\*Tests are Not Oracles\*\*: It cautions against viewing tests  |
| as infallible oracles, emphasizing that the true goal should be       |
| insight into how the system behaves.                                  |
|                                                                       |
| \### Recommendations for Effective Testing                            |
|                                                                       |
| 1\. \*\*Test Longevity\*\*: Keep regression tests for up to a year,   |
| but mostly at the system-level rather than unit tests.                |
|                                                                       |
| 2\. \*\*Targeted Unit Testing\*\*: Only keep unit tests for key       |
| algorithms that have a formal, independent oracle of correctness and  |
| significant business value.                                           |
|                                                                       |
| 3\. \*\*Prefer System Tests\*\*: If you can test something with       |
| either a system test or a unit test, the text advises opting for a    |
| system test as context is crucial.                                    |
|                                                                       |
| 4\. \*\*Quality over Quantity\*\*: Design tests with more care than   |
| the code they are testing.                                            |
|                                                                       |
| 5\. \*\*Turn Tests into Assertions\*\*: Where possible, it suggests   |
| turning unit tests into assertions within the code.                   |
|                                                                       |
| 6\. \*\*Discard Old Tests\*\*: It recommends getting rid of tests     |
| that haven\'t failed within a year.                                   |
|                                                                       |
| 7\. \*\*Focus on Development Practices\*\*: High test failure rates   |
| are indicative of the need to improve the development process,        |
| including perhaps shorter development intervals and better            |
| architecture.                                                         |
|                                                                       |
| 8\. \*\*Beware of Incentives\*\*: The text warns against rewarding    |
| developers for meaningless metrics like coverage, as it may lead to a |
| rapid decay in the architecture.                                      |
|                                                                       |
| 9\. \*\*Human Element\*\*: Finally, the text argues that tests alone  |
| don\'t improve quality; developers do.                                |
|                                                                       |
| The text overall encourages a more balanced, thoughtful approach to   |
| testing that is in tune with the realities and complexities of        |
| software development.                                                 |
+-----------------------------------------------------------------------+

11. 

```{=html}
<!-- -->
```
24. #### Anti-patterns

    1.  Flaky tests

        1.  What are flaky tests?

            1.  Flaky tests are tests that pass and fail randomly, and
                fail to provide useful information as to whether the
                underlying functionality is correct.

            2.  Flaky tests are bad. Avoid them at all costs, however,
                if there is a flaky test, triage it and file a bug for
                it appropriately. Understand how this impacts the
                overall test strategy. Perform the test manually in the
                meantime. It's important to not stop the build
                unconditionally on all flaky tests, because each test
                might have a different importance or priority, and it's
                important to acknowledge that tests themselves can be
                buggy. Running the test is an act of verifying if a test
                works, although this cannot be 100% proven because a
                test could still pass and not do anything useful.

            3.  It's important to not stop the build unconditionally on
                all flaky tests, because each test might have a
                different importance or priority, and it's important to
                acknowledge that tests themselves can be buggy.

            4.  Running the test is an act of verifying if a test works,
                although this cannot be 100% proven because a test could
                still pass and not do anything useful.

        2.  Why should I care?

            1.  The issue with flaky tests is that they have high
                entropy and do not reflect the underlying signal well.
                If it passes, then it works (? #review#), if it fails,
                then it might have had to actually fail or it might have
                passed. So, 50% \* (0-100%) which would be 0% to 50%. It
                also calls into question if the test is actually
                working, or if there's some underlying threading issue
                that could cause the test to stop working.

            2.  It also calls into question if the test is actually
                working, or if there's some underlying issue causing the
                unpredictability.

        3.  Why do they occur?

            1.  Non-deterministic inputs. For example, running a
                function with "A" and then "B" might cause it to return
                a different output.

            2.  Reliance on third-party resources. For example, querying
                a third-party weather API that might not be available.

            3.  Using a shared resource. For example, a database or
                trying to acquire a lock and those resources aren't
                available. Or, trying to read and write to a shared
                resource, which interferes with others who are using
                that resource, causing unexpected behavior.

            4.  Unnecessary element ordering. For example, verifying if
                the elements returned by a query match a specific order,
                when the order doesn't matter.

            5.  No version pinning. For example, installing the software
                "curl" without using a specific version, which means
                that the latest version is installed. The latest version
                may remove or add new CLI flags that make using the
                program different in between runs.

            6.  Dates and times. For example, doing calendar arithmetic
                or relying on certain dates to be true in order for the
                test to run. The test might be run on any day, at any
                point.

            7.  Different environment. For example, some of the
                resources that the test needs aren't available or are
                different.

            8.  Too granular or too fine-grained. For example, the test
                is too specific or not specific enough. If a function
                returns an array, the test could verify that the array
                contains the identical elements in the same order, a
                certain element must exist in the array, the arrays must
                be the same but order doesn't matter, the length of the
                array must be not zero, etc. These testing functions are
                highly different and allow for many different things to
                be returned. If one over specifies the test (i.e., the
                output's order doesn't matter) but the test is verifying
                that the output order matters, then the test might fail
                more often. Not specifying it enough, for example
                checking the length of the array, might mean that the
                objects are corrupted, but there aren't zero of them for
                example.

        4.  Handling and Mitigating Flaky Tests

            1.  How many times do I need to run my tests to make sure
                that they aren't flaky?

            2.  How do I fix them? Are there ways to proactively
                identify them? E.g., stress-ng? Are there any
                frameworks?

            3.  A source of test flakiness does not always 100% mean
                there is something wrong with the test. For example, a
                weird flickering UI that causes the test to think that a
                button isn't on the page is probably a usability issue,
                not a testing issue. It is possible to "plaster" over it
                and make the rest more resilient, but there might be
                deeper issues.

            4.  Identifying flaky tests, or tests that are too slow.
                Usually, publishing the test results can provide the
                information to a vendor-specific UI that can sort the
                tests by duration. From there in the dashboard, you can
                see which tests are slow. This might mean that you need
                to make the test more efficient, or break it up into
                smaller tests if it is testing too much.

            5.  If a flaky test cannot be easily resolved, quarantine
                it. This will prevent other developers from being
                blocked. The test should be fixed quickly to ensure that
                new code runs the test. Don't quarantine too many tests
                simultaneously because this means more and more code
                might not be correct and can cause an avalanche effect.

            6.  If a test can't be easily improved or requires
                additional research, consider adding a flaky annotation.
                This keeps track of the flaky tests and can allow
                automatic rerunning those tests. Some test frameworks
                can create a flaky test report, including how many times
                the flaky test failed to run and how many are currently
                running. The test can still run, but won't fail the
                entire test suite unless it cannot run a certain amount
                of times.

            7.  Consider deleting the test if it no longer serves its
                purpose, or a set of other tests cover it.

            8.  Consider refactoring or rewriting the test if there are
                too many changes to make it non-flaky.

    2.  #### Missing smoke test, set of tests to verify the testability of the build (BM7)

    3.  #### Testing is not fully automated (Q8)

        1.  "Concerning testing automation, the need for a
            fully-automated testing process (Q8) was considered
            important, because manual tests would be excluded from
            automated build within CI."

        2.  Counterpoints:

            1.  I don't agree with this point. Testing should not be
                fully absolutely automated, because fully automated
                testing ignores issues like usability, performance, and
                other human-nature issues that automated tests cannot
                find, such as exploratory testing. Testers should not be
                doing automated tests manually, however.

    4.  #### Production resources are used for testing purposes (Q7)

        1.  " Respondents considered as relevant the lack of testing in
            a production-like environment (Q1), while at the same time
            they considered dangerous the use of production resources
            for testing purposes (Q7). The latter has been also highly
            discussed in SO. Indeed, in a SO post, a user searching ". .
            . for the CI server to be useful, my thoughts are that it
            needs to be run in production mode with as close-as-possible
            a mirror of the actual production environment (without
            touching the production DB, obviously).". By analyzing the
            provided answers on SO, we found that "Testing environment
            should be (configured) as close as it gets to the
            Production." concluding the discussion by highlighting that
            "The best solution is to mimic the production environment as
            much as possible but not on the same physical hardware."."

        2.  10.1.1.7 is the act of testing production data in production
            (e.g., if someone does a SQL injection in production, the
            entire database could be erased, and this should have been
            performed on a production-like system so that customer data
            isn\'t risked). 10.1.1.12 is sort of a subpoint of 10.1.1.7,
            that is, the environment used to test doesn\'t mimic
            production closely so it\'s difficult to do the testing.

        3.  Counterpoints:

            1.  Additional testing resources can cost more money, and
                might be impossible (e.g., a spare rocketship to shoot
                into space.)

            2.  Testing envs can drift from the real-world unless
                carefully managed. This can cause differences in
                behavior.

            3.  Dedicated special testing accounts can exist in
                production instead of creating a testing environment.

    5.  #### Lack of testing in a production-like environment (Q1)

        1.  "About Quality Assurance, out of 14 bad smells, five
            received a positive assessment by the majority of
            respondents, and six more positive than negative assessments
            (see Table 8). Respondents considered as relevant the lack
            of testing in a production-like environment (Q1), while at
            the same time they considered dangerous the use of
            production resources for testing purposes (Q7). The latter
            has been also highly discussed in SO. Indeed, in a SO post,
            a user searching ". . . for the CI server to be useful, my
            thoughts are that it needs to be run in production mode with
            as close-as-possible a mirror of the actual production
            environment (without touching the production DB,
            obviously).". By analyzing the provided answers on SO, we
            found that "Testing environment should be (configured) as
            close as it gets to the Production." concluding the
            discussion by highlighting that "The best solution is to
            mimic the production environment as much as possible but not
            on the same physical hardware."."

    6.  #### Coverage thresholds are too high (Q4)

        1.  100% coverage on everything may create unnecessary tests,
            and 100% coverage does not mean the application is 100%
            tested.

        2.  Testing slows down the development process.

    7.  #### Coverage thresholds are fixed on what reached in previous builds (Q3)

        1.  Deleting code with 100% coverage can reduce total code
            coverage.

    8.  Tips on better test performance

        1.  Imagine there is a set of manual testing that is very slow
            that has to be done after all tests run. The manual testing
            has to be redone if it doesn't pass. To speed up the
            testing, one may initially look at making manual testing
            itself faster, however, one can improve the automatic test
            coverage (or do some quick testing beforehand) to rule out
            any issues

        2.  Manual tests take a very long time, and they can add up
            quickly.

        3.  Think about time management: even spending 1% of time on
            automating tests can quickly add up and free up even more
            time for automation.

        4.  Tests that never fail are not useless. This is because they
            offer a guarantee that the invariant is satisfied (unless
            the testing framework is broken.) Very important to note:
            the invariant must be identical to your goal, otherwise it
            offers false confidence.

```{=html}
<!-- -->
```
6.  ### Maintaining and analyzing test results

    1.  Correlating bugs with test cases (i.e., was there a test case
        that should have prevented this bug? If not, make one, otherwise
        if there was one, why didn\'t it catch it?)

    2.  Identifying flaky tests and slow tests

    3.  Automation potential and the role of QA tester

    4.  Test coverage and code coverage monitoring

    5.  Tracking test cases and disabled tests

    6.  The importance of a test repository

    7.  RCA (root cause analysis), in this case, if there was a bug in
        production, this means that it slipped past all of the tests and
        code review. Are the tests missing something or was it an edge
        case? This is useful for someone to explore.

7.  ### Automated vs. manual testing: a false dichotomy

    1.  Manual and automated testing is a false dichotomy because they
        are not mutually exclusive, and not all manual testing can be
        automated. Automated testing is automatic output checking, and
        manual testing is exploratory to some degree. Humans should be
        doing much more than automated output checking.

    2.  [[PREMIER: Michael Bolton: What's Wrong with Manual Testing? -
        YouTube]{.underline}](https://www.youtube.com/watch?v=DBzz04M01r8)

    3.  \*\*Introduction and Background\*\*:

        1.  \- Computers and people are good at very different things.

        2.  \- It is more efficient to allocate resources to a computer
            than to a human, to an extent. Computational resources are
            cheaper than a human brain manually accessing all code
            paths. People have emotions and aren't good with being 100%
            perfect.

        3.  \- The divide between automated testing and manual testing
            is a false dichotomy.

        4.  \- The terms \"manual\" and \"automated\" testing don\'t
            necessarily oppose each other; they aren\'t mutually
            exclusive.

    4.  \*\*Strengths of Automated Testing\*\*:

        1.  \- Automated testing focuses on automatic output
            verification.

        2.  \- Automation isn\'t just about efficiency but
            reproducibility and consistency.

        3.  \- Some automated tests might be infeasible for humans due
            to their complexity or need for extreme precision.

        4.  \- Automated tests excel when expectations are clear,
            deviations aren\'t tolerated, and code changes are
            incremental.

    5.  \*\*Limitations of Pure Automation and the Value of Human
        Testing\*\*:

        1.  \- Not all manual tests can be automated. Conversely, solely
            relying on automation is not optimal.

        2.  \- Things like usability, accessibility, and functionality
            testing can't easily be evaluated by automated tests.

        3.  \- In software development, tacit knowledge is knowledge
            that is embedded in your framework but is difficult to
            explain.

        4.  \- At this point in time, it's not possible to program a
            computer with tacit knowledge.

        5.  \- An automated test can only know if something is wrong if
            it can compare it to an internal expected value, provided by
            a human.

    6.  \*\*Exploratory and Human-centric Testing\*\*:

        1.  \- Testing is an exploratory procedure, and its insights are
            tacit knowledge that can\'t be captured purely through
            demonstrations.

        2.  \- Exploratory testing is essential to uncover bugs that
            automation might miss.

        3.  \- Human testing allows the evaluation of whether an
            application meets non-quantitative standards.

        4.  \- Testing is inevitable; even writing code involves a type
            of manual testing. Verification often happens through PR
            reviews.

        5.  \- Human testing emphasizes its experiential, exploratory,
            speculative, responsible, and growth-centric nature.

        6.  \- Experiential testing involves the tester interacting with
            the product as users might, while exploratory testing has
            the tester making choices based on their agency.

        7.  \- Testers need immersion in the user\'s environment to
            genuinely grasp user needs, spotting bugs, and suggesting
            potential upgrades.

        8.  \- Speculative testing involves human testers being curious
            and asking questions, in contrast to demonstrative testing
            that proves specific aspects.

        9.  \- In responsible testing, human testers are accountable for
            the work quality. In contrast, with machine testing, the
            onus lies with the machine or tool creators.

        10. \- Growth in human testing refers to the continuous
            learning, ideation, and risk identification by testers.

    7.  \*\*Conclusion and Call to Action\*\*:

        1.  \- Automation should enhance human responsibility, and tools
            should serve as aids, not replacements, for human expertise
            and judgment.

        2.  \- It\'s essential to recognize the specific nature and
            advantages of both approaches.

        3.  \- The term \"manual testing\" can sometimes portray a
            negative image of human testers who aren\'t coding. Thus,
            precise terminology is crucial to communicate their role.

        4.  \- Instrumented testing was introduced, suggesting that a
            medium influences the tester\'s interaction with a product.

8.  ### Developing a test strategy

    1.  What is a test strategy?

        1.  A test strategy defines a framework on how to allocate
            business resources to do testing, including how and which
            tests to write, and when.

        2.  To boost developers\' confidence in their changes, tests
            should be meaningful and well-constructed to avoid a false
            sense of assurance. Writing code that passes tests does not
            mean that the code is correct. It just means that it passes
            the tests. If the tests are designed well, then it can also
            verify the correctness of the code.

        3.  

    2.  How do I know what to test?

        1.  Tests are great. Let's test everything given that we have
            AI-based tools to do this for us, and can generate tests all
            day. Can we do that? Conduct a thorough human review first,
            then automate tests for all elements and interactions,
            including visuals and functionalities. Assume this is
            feasible.

        2.  The issue is that you have to create new features in your
            application, or modify existing functionality to continue to
            meet business requirements. Those tests would break
            immediately, and so you would have to use your own judgment
            to evaluate whether those tests broke *because* of something
            intentional (i.e., adding a new feature), or something
            unintentional (i.e., a bug.) In effect, there's no way of
            getting out of human judgment. You could get the AI to
            rewrite those tests if they failed, but this would negate
            the purpose of the information gained from the feedback of
            the tests.

        3.  It would also incur a large compute cost if you were to test
            *everything*. This would inevitably slow down the
            development process significantly.

        4.  It does cost more to fix bugs in production, but it costs
            even more if features are delayed (and thus your competitors
            get to you first), or, the revenue generated from the new
            features if they were released sooner.

        5.  But things are a bit more complicated. This would imply that
            you must write tests 100% of the time, thus, there would not
            be a way to release any features, because there is still
            more testing to be done. So therefore testing must be
            subject to constraints. This calls into question the value
            of testing, and how to maximize the value or worthwhileness
            of the tests. This involves creating a test strategy in
            order to figure out which tests to write, and how to write
            them.

        6.  You could argue that if your application never had to
            change, then you should write lots and lots of tests for it,
            and the above would apply because you wouldn't have to
            modify existing functionality. But verifying something that
            is already present is a one-time task if it will never
            change. Writing automated tests for it that run once are
            useful, but are of limited use. They've run once, and it was
            a lot of work.

        7.  This provides the foundation for a testing strategy: how do
            we efficiently use our resources to test?

        8.  Really consider how much testing that you want to do. It is
            disappointing to see an application fail, but how bad is it?
            Is someone going to die, or is someone just going to get an
            error page?

        9.  If people are very sensitive to bugs, do they also want lots
            of features, or are they also conservative in that aspect?

        10. Be pragmatic when writing automated tests. If you have a
            mature project that isn't changing often, then these types
            of tests are useful. If you have a fast, startup project,
            then automated testing might cause unnecessary drag and
            provide too many guardrails for functionality that will be
            continually changing. When in a startup, the priority is to
            get features created with the risk that they might fail (and
            thus have to be tested in other means), given that they
            change often in response to customer feedback. Creating
            automated tests for a product that might not exist in the
            next few months could be considered wasteful.

        11. Look at your previous bugs. They exist because they slipped
            through the entire testing procedure and quality control.
            How can your test strategy be revised? Are these critical,
            customer bugs or just small bugs? Be careful not to overdo
            it on testing if these bugs were non-critical in nature or
            had minimal customer impact. The goal for CI/CD is to
            release changes quickly, at the cost of sometimes making
            mistakes, which should be easily reverted.

        12. Should I write a test for it? If it can be demonstrated like
            a chemistry experiment, then yes. If you are sure of its
            outcome and can specify it concretely. The more ambiguous
            the outcome the more difficult it is to write tests for it.
            For example, early on in a software's lifecycle with lots of
            changing requirements.

        13. What types of bugs are being found in production? Are they
            requirements-oriented bugs? Are they simple to automate
            bugs? Are they usability bugs? This can help narrow down the
            issue. Specifying requirements right to the letter is a bit
            annoying, you might want to consider adopting Agile to make
            it a bit easier for people to understand the big picture.
            Otherwise there are too many instructions, and you have to
            continually specify more, and more, and more instructions to
            which people follow it right to the letter. It's a vicious
            cycle.

        14. How large are the bugs in production, are they catastrophic
            or just something small, like the color of some text? There
            are some ways to prevent regressions, like screenshot tests.
            If they are catastrophic, then you might want to do more
            demos to make sure that the features are coming along as
            expected and use shorter development cycles. This is sort of
            like Agile.

        15. Should I write a unit test for a homepage?

            1.  Will it be tested through manual testing already? In
                this case it might not be needed.

            2.  However, automated testing will prevent any features
                that cause the homepage to stop working. This means it
                can be caught earlier in the development process.

            3.  Why not write tests for everything, as it is valuable
                that it can be caught earlier in the development
                process?

                1.  Tests take time to run and to write

                2.  Tests have to have a concrete output, for example,
                    usability is very abstract and a test doesn't know
                    how to measure or quantify that. There is
                    accessibility testing, but it can't catch
                    everything. Things that require subjective judgment
                    are important to be tested manually.

                3.  Tests can test things that are difficult to manually
                    test, except they can be done automatically.

                4.  Some things cannot be manually tested.

                5.  Might be covered indirectly by other automated tests
                    or through manual testing

                6.  Might not be worth it to the end customer.

                7.  Customer expectations

                8.  Final goal: Risk assessment and extent that things
                    have to be rolled back if there was an error
                    introduced earlier in the process.

            4.  Test strategy might be too abstract for some, and might
                not have necessary information on how to create the
                strategy (e.g., integrations with other teams and their
                future plans)

            5.  Test strategy can be applied recursively as if it was a
                fractal, each of those sub-tests can also have multiple
                variables and values that can be strategized to do more
                comprehensive testing. For example, an application
                contains multiple attributes. The most important
                attribute is selected for testing. But what values
                should you use to test it? If the application is a black
                box, it is unclear what data to use, and testing might
                be inefficient and the strategy is not as good.

            6.  Testing machine learning applications should begin by
                only providing suggestions when the model is highly
                confident. This can help maximize user trust. A
                spell-checker is given as an example.

            7.  Too much testing can be counterproductive. For instance,
                when adding a new field on a login page with 1000 tests
                can result in a significant number of tests failing.
                Correcting all the failed tests can be a time-consuming
                and challenging task, especially when dealing with
                strict deadlines.

            8.  Without testing, the business may have to rely on
                indicators such as customer feedback, non-functioning
                demos, delays in product or service delivery, and
                unfulfilled app needs to evaluate the system\'s
                efficiency.

            9.  The text raises a question about the balance between
                relying on customer feedback for testing versus doing
                in-house testing. This could be influenced by several
                factors, including the risk associated with the product
                malfunctioning (e.g., life-critical systems like
                pacemakers).

            10. Startups often need to assess market fit more frequently
                than larger companies, which presumably have already
                established their market fit.

            11. The text suggests that a company\'s approach to product
                testing and market fit assessment is influenced by
                factors such as organizational strategy, corporate
                governance, and corporate ethics.

            12. Products marketed as beta versions may bypass some
                ethical restrictions and product usage requirements,
                although this may depend on the industry.

            13. A company\'s reputation is closely tied to the quality
                of its products. If a product is so poor that people
                refuse to use it, customer feedback may become
                irrelevant. Customers typically do not provide feedback
                on the company\'s vision, long-term goals, or security.

            14. Meeting product expectations is essential for ensuring
                future market share and business success, aligning with
                corporate strategy. Testing is, therefore, necessary to
                ensure the product\'s quality and usability.

        16. Can someone who doesn't know how the application works write
            tests for it? What does that show about the tests? For
            example, is it just running the code and taking the outputs?

        17. Failing tests can bring changes up to your attention, but
            cannot differentiate between intentional and unintentional
            changes.

        18. If you have 1200 unit tests, and your application is
            completely broken, and not a single test failed, then you
            may have to revisit your test strategy.

        19. If something is important, test it. Don't make excuses that
            it is hard to test, refactor it to that it is easier to test
            it.

        20. When things are taught, it's easier to make hard rules if
            the person doesn't know better. For example, children are
            taught not to touch a hot stove, when in reality a stove
            could be of any temperature. There isn't a good reason to
            touch the stove, and the nuance is difficult to convey.

        21. To some extent, tests can be diagnostics, however
            diagnostics are for after-development to diagnose issues
            (e.g., asserts) so tests can theoretically help you to tell
            you what's wrong if there is an issue during development
            (e.g., the login pages fail, therefore there's an issue with
            the login.)

        22. Questions to ask prior to testing things:

            1.  What is the probability that this does not complete the
                user's goal?

            2.  How much testing is required to adequately meet
                customers expectations?

            3.  What is being added/modified, and to what extent does
                that touch other components? How big is the testing
                scope?

            4.  Not as important to test in depth early on when things
                are vague as a lot of it might be thrown out, and
                customers may have not have had time to explore all
                areas of the product that have yet to be tested, and it
                might be unclear where the customer's testing pain
                points are

            5.  Not all risks are quantifiable, how do we keep track of
                the other ones such as usability?

                1.  Performance can be benchmarked against common
                    benchmarks, although users may have different
                    performance expectations.

            6.  Make sure to not misunderstand metrics: for example,
                page view time that is high could signal that
                documentation isn't good (as people are having a hard
                time finding what they need)

            7.  Unchanged features are misleading not to test because
                the application is treated as a black box, and there
                could be multiple unnecessary hidden dependencies
                between multiple components (i.e., due to tech debt)

            8.  Should one spend a little bit of time testing the
                non-high pri things? This helps reduce uncertainty, as
                if there is no testing at all, then it is unclear if it
                might be more buggy than expected

        23. If there are too many tests to run, then a subset of the
            tests can be randomized and run instead which can allow them
            to run more frequently

        24. Small items that are not risky can have a large impact on
            customer experience. For example, if a small UI element is
            not accessible or is unresponsive, and is used often as part
            of another workflow, then this can detract from the customer
            experience.

        25. May want to discern between someone actively looking for
            bugs via exploratory testing vs. reporting bugs while using
            the application, as if someone accidently hits a bug while
            using it then it is more likely that other bugs exist,
            whereas if someone is going out of their way to trigger
            something, then it's less likely. This is because of a
            normal distribution of bug patterns.

        26. The definition of done and testing go hand-in-hand. For
            something to be considered done, there has to be at least
            *some* testing done, whether manual or just by creating the
            feature, to make sure that it is something users will
            recognize and are able to use. For example, the feature may
            be documented, or marketers may want to use the feature to
            sell it. Demos of the product for potential clients.

            1.  Even if you can write your feature perfectly, there is a
                chance it could be broken by an unrelated change that
                you have no control over. Therefore, testing is good to
                be defensive.

        27. Mutation testing (counteracting poor unit tests)

        28. If you write a test strategy that involves lots of E2E
            tests, then that's ok, even if they're slow. Don't
            necessarily worry that they're slow right away. Instead, you
            can split up the test such that it covers the same
            functionality as that E2E test, or, however you want the
            implementation: whatever technical implementation
            sufficiently provides confidence in what you're trying to
            test, so that could be some E2E tests, maybe some unit
            tests, or maybe just lots of E2E tests.

    3.  #### What is happy path testing?

        1.  Happy path testing is testing the desired path that the user
            does to complete their goal. The user is perfect: they type
            in the perfectly correct data, click on the perfect buttons
            in the perfect order, and wait the perfect amount of time.
            No errors are triggered during their session. For example,
            in an installation wizard, this would involve the user
            clicking "Next", and agreeing to the terms and conditions.
            This is useful for software used by professionals as they
            are very familiar with the software, thus, they might
            benefit more from these types of test cases.

        2.  Signs that you might be doing too much happy path testing is
            that if the user clicks on anything else (for example, the
            Back button), then the application crashes or produces
            incorrect results. The user must click on everything in the
            exact right order, and if an operation can be performed
            twice, then the user might not be able to do it because the
            test only checked if it could be performed once.

        3.  This is important because users are unlikely to be as
            familiar with the application as developers, thus, they
            might click on other items in an attempt to understand the
            application, explore its functionality, or by accident.

        4.  To fix this, you may want to make your business test cases
            more fuzzy. For example, the user is allowed to add as many
            items as they wish (up until the maximum of 100 which is
            allowed in the UI for example) in this list. Then, the test
            can randomly choose between 0 and 100 items to add. The test
            should, however, log its seed somewhere so that, if there is
            an issue with the tests, then they can be reproduced.

    4.  #### What is sad path testing?

        1.  Sad path testing occurs when you test things that the user
            might do, but cause an error. For example, the user would
            like to transfer -\$1.00 to their bank account. This isn't
            possible, so they should receive an error message.

        2.  Signs there might be too much sad path testing is that the
            users are unable to complete their goals without errors.

    5.  #### Test the things and level that matters and issues with testing pyramid

        1.  One of the ways that people create a testing strategy is to
            reference the testing pyramid.

        2.  ![A diagram of a service unit Description automatically
            generated](vertopal_7cf17b12d305426e8597d711f8f376f6/media/image6.png){width="3.1828477690288715in"
            height="1.705097331583552in"}

        3.  The testing pyramid is a guideline or suggestion on how to
            distribute the types of tests that you are writing. In this
            case, there should be fewer UI tests, and more unit tests in
            general. This is not a useful model, even if it is generic.
            This is because it enforces the technical solution before
            the business requirements. **Test where it makes sense.**
            **Do you need UI tests? Write them. Do you need unit tests?
            Write them.**

        4.  **The issue with the testing pyramid is that it is
            misconstrued to suggest writing different types of tests
            divorced from business requirements, when it might not make
            sense.** Don't write a bunch of unit tests just because you
            have a lot of UI tests to make the pyramid fit.

        5.  Think about where things need to be tested at, and then do
            the technical implementation. Don't think "oh, I only have
            one e2e test, I should write more".

        6.  From "Death of Inspection by Sachin Natu"

            1.  Find out where the bugs are coming from. Does it make
                sense to test the UI layer if there are data issues
                coming from a layer beneath? Consequently, does it make
                sense to add more unit tests if buttons are not working
                or the text isn't rendering correctly?

            2.  If the team owns quality, what is the role of the
                tester? Testers may feel threatened if they are no
                longer needed. However, they should be working on
                higher-order tasks such as evaluation rather than just
                checking. This means that most of the tests could be
                automated, and they will then have more time to spend on
                doing higher-level checking that can't be easily covered
                by automation. Think about the bugs that the testers are
                reporting, and see if they could have been covered by
                automation, look at the root cause of the bug (e.g., git
                bisect.) For example, a form displays incorrect data.
                The form just displays whatever is given to it, then as
                you go down you find out that a function computed the
                wrong result. It doesn't make sense to add a UI test
                here, because the root cause of the issue was with the
                function, not the form.

            3.  If a test is at a certain layer, ask why and check if it
                should be pulled up or pushed down to another layer. Is
                there a more simple way to write the test?

            4.  If there are going to be testers, then they should have
                a development background and be able to work on
                real-world problems and also work with developers, and
                may even have to conduct interviews with stakeholders to
                get business requirements to determine what is
                important.

    6.  Code coverage and mutation testing can help "bleed" the edges of
        a graph or a point on a target to get higher coverage, but it is
        not a substitute for a good test strategy. This is because it
        only diversifies around its point but wide brush strokes can
        cover much more easily, although not as thoroughly. [[Coverage
        is not strongly correlated with test suite effectiveness \|
        Proceedings of the 36th International Conference on Software
        Engineering
        (acm.org)]{.underline}](https://dl.acm.org/doi/10.1145/2568225.2568271)

    7.  ![A screenshot of a computer screen Description automatically
        generated](vertopal_7cf17b12d305426e8597d711f8f376f6/media/image7.png){width="6.5in"
        height="3.611111111111111in"}

    8.  [[(1) A Practical Example for Using AI to Improve your UI and
        API Testing -
        YouTube]{.underline}](https://www.youtube.com/watch?v=68mEgr0vO64)

    9.  #### On testing strategy as a fractal

        1.  ![A white circle with orange and yellow lines Description
            automatically generated with medium
            confidence](vertopal_7cf17b12d305426e8597d711f8f376f6/media/image8.png){width="3.151042213473316in"
            height="2.363280839895013in"}

        2.  ![A white circle with orange and yellow lines Description
            automatically generated with medium
            confidence](vertopal_7cf17b12d305426e8597d711f8f376f6/media/image9.png){width="3.1811712598425195in"
            height="2.391042213473316in"}

        3.  ![A white outline of a purple background Description
            automatically
            generated](vertopal_7cf17b12d305426e8597d711f8f376f6/media/image10.png){width="3.17044728783902in"
            height="2.3739818460192477in"}

        4.  You can keep zooming in more and more and more, and there's
            infinite layers. But if you start zooming into the wrong
            spot, then you will never be able to course-correct. Also,
            once you have a high-level plan, there are multiple stages
            for resource prioritization such as efficiency improvements
            and how/what to test, that come later after business
            requirements have been ascertained. Therefore, if you are
            working on the wrong project, it doesn't matter how
            beautiful your testing strategy is, the project is useless.

    10. #### Tips on choosing the type of test to write

        1.  Too many unit tests (and not enough E2E tests) can lead to a
            patchwork approach. Things work in isolation, but not
            together. Event handlers for submit buttons for example
            aren't hooked up, and clicking on buttons doesn\'t do
            anything yet all of the unit tests pass. It is much easier
            to write a theoretical unit test than a non-practical E2E
            test.

        2.  Tests whose external dependencies are mocked are still
            useful, but less useful. At some point, you want to mock the
            external dependencies. If the external dependencies are that
            flaky, then something is wrong with those dependencies and
            your customers might not be happy. If you're retrying it in
            prod, retry it in your tests. If it's slow, well, depends on
            business needs. It might be slow for your customers too,
            depending on how comprehensive your tests are, of course and
            how much you're testing it.

        3.  Imagine you are building a calculator that contains many
            internal wires to perform computations. This calculator was
            created sloppily, and some of the wires are unintentionally
            crossed, however, the output is still correct based on the
            E2E tests. Should the calculator be trusted? In this case,
            it would make sense to make unit tests because the
            implementation details have already been guaranteed to work,
            therefore, deviation from those implementation details may
            or may not cause the calculator to malfunction.

        4.  Unit tests or different types of tests should be an
            implementation detail in and of themselves stemming from a
            proper test strategy.

        5.  Are we testing the outcome, or do we need to know *how* the
            application is producing that outcome? For example, imagine
            we are checking if a cache works correctly. The process as
            to which the data is fetched is more important than
            returning a value (although that is important as well.)
            Checking the output does not verify the cache works
            correctly because there could be no cache and a value could
            still be returned. If the outcome was XYZ, does it matter,
            in any shape or form, how it was generated? Could it have
            gotten the value from anything at all? In this case, a unit
            test would be more appropriate.

        6.  Or, for example, say there is a shopping website. You place
            an order and then get a receipt. Unbeknownst to the
            customer, there is some important recordkeeping, such as
            audit logs, etc. In this case, mocking is helpful because
            you want to know if those functions are called. This might
            involve creating a unit test, because the application is
            unlikely to expose this functionality to the customer.

        7.  On the other hand, sometimes the outcome is more valuable
            than the process. For example, say I want to render a button
            on the page and I want to check if the user can click the
            button. I don't care what size, shape, dimensions, or text
            rendering or click handlers (or what the click handlers are
            doing), I just want to know if the user can click on it and
            they will go to the next page. It would be impossible to
            know where that button is on the application, since only
            testing it in isolation means that it does not have any
            interference with anything else that could exist. Therefore,
            the outcome matters and I don't care how the button itself
            is rendered, just that it exists and the user can see it and
            can click on it.

        8.  Testing whether a chosen item has been randomly chosen could
            be a good one for implementation testing or e2e testing, so
            it depends. You could run the function thousands of times
            and then you would be assured that the distribution is
            within a certain tolerance (granted, the probability of
            winning the lottery would be higher) although this requires
            many thousands or tens of thousands of trials and the
            potential for the test to be flaky. However, you could test
            the implementation details and mock the random function to
            return non-random numbers, but this does not guarantee that
            the random function has been implemented correctly because
            you could divide the random by itself to always get one.

        9.  There is too much focus on which type of test to make versus
            knowing what to test and how to test it. There is also too
            much focus on merely reducing E2E tests because there are
            too many. What constitutes too many? Is it slow? If so,
            engineering tasks should be secondary to ensure quality.
            There are many optimizations that can be made to E2E tests,
            including running them later, less frequently, prioritizing
            them, etc.

        10. Use mental models. Think about the opposite situation. What
            criteria would the cache not work, how would I test for
            that?

            1.  For accessibility testing, consider doing it async,
                where you deploy something and then find the bugs. The
                issue is that it does make the process for fixing the
                bugs slower but if someone skilled is required to fix
                them then it can help unblock new work, and can help
                prioritize which accessibility bugs need to be fixed.
                Doing testing on each PR would be very time consuming.
                Therefore, QA should test a batch of changes at once,
                with some indication of what new features were added.

    11. #### Are tests that never fail always useless?

        1.  A test that never fails is not always useless. The fact that
            the test always passed is feedback and showed that that
            scenario was successful and instilled confidence in your
            changes. Tests can also be used for examples and
            documentation.

        2.  One could argue that you should write a test that fails
            first, and then make it pass, thus showing that it is valid
            and thus useful. However, one can still write a useful test
            that passes without having to fail first, and can verify
            that after the fact. Even if it was, there isn't a way to
            predict with 100% certainty if it would have failed, so the
            cost has already been paid and thus unrecoverable. It
            provided assurance that the validation was successful,
            similar to an insurance policy that you never pay out. It
            allows you to take risks that you otherwise wouldn't have,
            which is difficult to quantify, given that tests are
            designed to provide confidence. You've written some code for
            a function that has tests, those tests never failed, but
            they ran on your changes, giving you confidence. You can
            also use the fact that the test was passing to help with
            debugging: if only one test failed, and another one didn't,
            then you can logic-ify your way to figure out what the issue
            was. It's also useful for docs, too, like example code. The
            expected value is higher, because the probability of a bug
            occurring is non-zero, and the benefits of a test is
            non-zero (assuming that it is not trivial.) Are airbags that
            are never deployed useless? Would you want to drive a car
            without airbags, assuming an identical option with an
            airbag?

        3.  The intuition behind the fact that if none of the tests
            fail, then they are useless is because programmers make
            mistakes, and tests are designed to prevent them. Given that
            you're very likely to make mistakes, and the fact that the
            tests never triggered means that you're an excellent
            programmer, or the tests aren't great.

        4.  This usually stems from the impression that tests are
            designed to catch defects, and if they don't report any
            defects then they are not useful. This isn't correct,
            because the ability to catch defects is different from the
            defect occurring, and reporting it. Reporting a defect could
            mean that the test is invalid, there is no defect. If I have
            an assembly line that produces widgets, and I have a test
            that ensures that they are at most 3cm tall, and the company
            stops creating those widgets at some point in the future,
            the test never failed, then was it useless? The absence of
            the test doesn't make the widgets suddenly change their
            heights, thus, in retrospect, if the test was removed, it
            would have not changed the output. Let's consider we went
            back in time and removed the test. Would we be able to have
            the assurance that the widgets are at most 3cm tall? What
            would happen if they are taller than 3cm? It is possible
            that the check itself was not necessary, as it doesn't
            matter how tall the widgets are. But if there is a risk of a
            recall for widgets taller than 3cm, and the fact that there
            is assurance that that can't be the case, then the business
            can mitigate that risk. While hindsight is 20/20, it is
            important to create effective tests, otherwise they are not
            useful.

    12. #### Risk-Based Testing

        1.  testing just based on risk might have some caveats, namely

            1.  Could be remedied by using mental models instead to
                identify risks, although there is a risk that only
                evidence that is associated with your priors is accepted

            2.  Testing via risk is a good value to effort, value curve,
                however, degrades rapidly when there is a larger scope
                of items to be tested

            3.  After large risks are addressed, it may be difficult to
                finely-prioritize smaller risks because they are too
                small and might not fit within the risk framework
                nicely. For example, non-functional requirements
                (although this could be tangentially related to consumer
                risk, as if the product is too slow then people might
                not want to use it based on industry benchmarks.)

            4.  Shaped by industry as well

            5.  Customer experience could theoretically be a "risk" but
                if customer experience is poor then tests might neglect
                it

            6.  Is it risk-based to test a feature after it has been
                completed to ensure it works as expected?

            7.  Testing to meet laws and regulations is a risk-based
                endeavor because failure to comply with those
                regulations can lead to fines

            8.  A risk-based approach would say that only feature A
                should be tested, even though all other features
                compromise more of the application holistically. For
                example, feature A is used 40% of the time, feature B
                10%, feature C 10%, feature D 10%, feature E 10%,
                feature F 10%. Here, features B-F are 60% of the share,
                while feature A is only 40%. Depending on how you slice
                risk, since it is subjective, then this might be missing
                out.

                1.  Alternatively, it can be spread out among the
                    long-tail of the distribution. Or, prioritized to
                    clients that spend more money (so that you can make
                    sure that the people that are spending lots of money
                    get a good experience.)

                2.  Each feature may be used by multiple customers, and
                    the larger features may have less complexity, so it
                    might have less inherent risk.

                3.  More people using a specific feature may also reveal
                    more bugs sooner (e.g., during beta testing), so
                    over time it may have less risk if it is well-tested

                4.  Ultimately, any framework is shaped by politics, so
                    do be aware.

            9.  Exploratory testing can mimic customer behavior, and
                could have better coverage. This is because it is not
                possible to predict with 100% accuracy what will be the
                most popular feature, or what customers are likely to
                use or how they interact with the system. Exploratory
                testing doesn't have a risk profile per-se or goals
                associated with it, so it can be difficult to know how
                to accomplish this. It's unlikely customers are robots
                that precisely perform every activity precisely as in
                the test.

                1.  Exploratory testing could be called "testing the
                    risk of the unknown", but the risk wasn't assessed
                    beforehand so it's unclear what exactly is being
                    tested

            10. Risks are inherently biased, so need to figure out a way
                to make them less biased

            11. To overcome some of the challenges, use risk to identify
                high priority items and make sure those are tested.
                Then, divide the remaining items using another framework
                that is not risk-based.

        2.  #### Issues with a purely risk-based focus

            1.  The maximization of short-term utility via risk-based
                planning can produce a local minima in high resource
                environments as long-term goals may not have immediate
                short-term policy rewards.

            2.  Everything in testing isn't about risk, because risk is
                not ontological. You can't see risk, it is not concrete
                and it is always relative to something else, or as an
                undesired behavior. For example, saying that bad
                performance equals performance risk is true, but it
                misses the fact that risk is relative and subjective,
                and this is only a stepping stone.

                1.  This argument can also be made for any attribute, as
                    everything derives from a core concept, it does not
                    mean that it is rooted inside of it.

                2.  Testing should assess performance, because bad
                    performance would mean a performance risk. It's too
                    far removed from what a risk is, because a risk
                    isn't well defined because it is a concept, not a
                    thing or a concrete measurement, or something that
                    can be derived from.

            3.  Knowing risks and mitigating them are two separate
                things. For example, if a test finds that a very strange
                sequence of characters (or a very long sequence) causes
                something to break, but fixing it would be very time
                consuming, then the business may not proceed with it.
                However, they should be aware that this is being
                deprioritized.

            4.  Testing is about risk management.

                1.  What is the risk of letting a security issue get
                    released?

                2.  "A risk premium is a measure of excess return that
                    is required by an individual to compensate being
                    subjected to an increased level of risk." Wikipedia.

                    1.  Excess return means that time spent working on
                        the product now will have a much higher ROI than
                        in the future.

                3.  One could argue that startups are less likely to
                    benefit from tests because they don't have a product
                    yet that can be tested, and don't have a clear
                    understanding of their customer requirements. This
                    means that preservation of future cash flow is
                    undetermined because there is none, whereas large
                    companies may have many contracts and evidence that
                    there are customers already that use the products.

                4.  Customer expectations for a startup or new product
                    might be lower, or they might be able to compensate
                    for their expectations based on what value that the
                    product provides to them.

                    1.  Risk appetite and risk premium. For example,
                        startups are willing to risk it all, sometimes.
                        It would depend on the startup's goals and
                        current industry (for example FinTech doesn't
                        like low testing.) There could be high
                        competitive pressures as well.

                    2.  Large companies want to preserve existing
                        customers who are happy with the product, so
                        want to make sure that the product is stable and
                        may benefit from more tests. However, if a large
                        company is threatened by competition, then it
                        could be less likely to create tests because
                        more effort has to be put into making a
                        competitor versus testing it (which slows down
                        development.) If the company misses the
                        competition, then it risks a business
                        opportunity, and so making sure it is well
                        tested might be less relevant because the
                        customers may want a large amount of changes
                        anyway. This means that it is unclear what has
                        to be tested, and might be too abstract.

                    3.  Brand and image as well, large companies have
                        more to risk.

                    4.  Does it make sense to verify a typical customer
                        scenario if it can be manually verified? How
                        much testing overlap is needed?

            5.  Performance could be deprioritized in a risk-based
                situation. This means that larger customers, depending
                on how the algorithms process their data, could receive
                much longer response times or poorer performance.

                1.  Counterpoint: companies selling the software can
                    push the costs to the purchasers by making them
                    purchase expensive hardware which will run their
                    application more smoothly, or, create consultants
                    who can fine-tune the system based on their needs

            6.  Long-term investments (provided that more resources are
                available) can prove to have a higher ROI, but require
                very smart and thoughtful strategic planning. Their
                effects may not be immediately visible in the
                short-term, and the long-term might be too abstract to
                fully understand the consequences or benefits.

            7.  Assessing user platforms based on risk is not very
                innovative (i.e., choosing what audience to cater to or
                to test for) because this excludes people who aren't
                using their devices because the software doesn't work on
                those devices. For example, say there is low macOS
                usage. Then, it would be deprioritized in testing, and
                would continue to become lower over time because there
                would be fewer resources dedicated to it. This could be
                a market that could be important, but it is unclear due
                to prior decisions. Even with more testing, there is a
                very large momentum that has to be broken for people to
                begin to use the app again. There is a high upfront cost
                to start testing on new platforms, however.

            8.  Risk is logarithmic, which means that lower-prioritized
                items have higher uncertainty about how much risk they
                will have, and so decisions to sub-prioritize those
                might not be useful because arbitrary decision-making
                processes may be required as the quantitative risk is
                too similar to understand which ones should come first
                because each item would have a small amount of standard
                deviation or error to its estimates.

            9.  Talk about game theory and risk taking, and the extent
                that the utility curve is concave

            10. [[Pseudocertainty effect -
                Wikipedia]{.underline}](https://en.wikipedia.org/wiki/Pseudocertainty_effect)
                is a risk when creating the risk matrix because one
                might overestimate expected value depending on prereqs,
                even though both decisions are the same (cognitive
                bias.) Solution is to involve more stakeholders.

            11. If everything is high risk, then nothing is important.
                It is possible that everything is equally as important,
                however, although this might mean that you're
                underestimating the scope and features of the
                application, and missing non-functional requirements.

            12. Lower risk items, by definition, do not require the
                attention of multiple stakeholders to prioritize finely
                because they are, by definition, low risk. Risk-based
                activities can be complex, and so there is a risk that
                too much time is spent on risking meetings.

                1.  Time is spent more efficiently if testers can create
                    a testing plan for the low risk items. This is
                    because finer priorities that have lots of detail
                    may be difficult to communicate at a high-level to
                    multiple stakeholders. It may also require a
                    comprehensive but shallow testing plan to do "canary
                    in a coal mine" testing to quickly identify any
                    issues with some of the features that would prohibit
                    them from being used correctly. These issues can
                    then be sent back to the stakeholders for review.

    13. #### When should a test fail?

        1.  If the user's goals are no longer possible

            1.  Is a user going to click on a button based on its ID
                selector? Probably not, but there has to be a way to
                unambiguously refer to a button. However, that button
                might not be visible on the screen.

            2.  What about a button's content? This is more flexible,
                but if the button was moved to a strange position, then
                the text will not catch it.

            3.  There is a gradient between when a test fails and
                succeeds. Something could be moved by a few pixels, or
                more, or change color and be ok, but sometimes it might
                not be (for example, a bad CSS style.) It is up to the
                program to designate a threshold for this. Is it better
                to fail just in case, or is it too much work to fix the
                tests?

            4.  How much time should I be writing tests vs. creating
                value for the customer? Tests should be able to be
                manually bypassed if needed (e.g., programmer manually
                checks if test is working, or convert it to a manual
                test while the test is being worked on)

            5.  This overlaps with auditing (i.e., do a shallow test and
                see if anything fails) rather than selectively testing
                one component (and then critical components might fail
                but you would not know.)

    14. #### Organizing tests

        1.  It is important to categorize and name your tests well. This
            is because

            1.  It prevents duplicate tests and can help create more
                effective tests by identifying what components are
                tested, and to what extent

            2.  If needed, a test can be run manually and the steps
                should be very clear. This can help debug any issues
                with the test, or, if there is something wrong with the
                test runner. Note that some testing frameworks can
                provide guidance through UI prompts and videos on what
                exactly is being tested, and at every step, so this
                could be helpful

            3.  Other people will be extending the tests. They have to
                know where in the flow they need to modify entries.

        2.  Application code has to run in order to be tested, but to
            what extent?

            1.  Mocking and stubbing can mean that not all of the
                application code runs, and third-party APIs also
                complicate things as well as it is unclear how these are
                connected.

            2.  If a code path is not executed, then it will have an
                unknown state because nothing has run it. However, the
                unknown state is likely, to some extent, to be known
                upon inspecting the code.

            3.  Code coverage is about verifying that a subset of the
                paths through the code meet the expected behavior. This
                does not mean that the expectations are correct, nor
                does it mean that the behaviors of the code are covered
                either. It just means that the paths in the code meet
                the expectations that were provided in the tests, so the
                expectations would have to be correct.

            4.  The next thing is there could be a combination of states
                that might not be possible to know if they are tested
                through code coverage. For example, sequences of methods
                that run in different orders that can set up certain
                things to trigger.

            5.  Code coverage could be a better proxy in stateless
                applications, where a single function or method is
                tested and does not retain any state. For example, in
                unit tests or when a single function has a set of zero
                or more inputs and a set of zero or more outputs and
                does not change its environment, and is idempotent and
                immutable.

    15. Other stuff

        1.  [[Too Much Test Automation \|
            StickyMinds]{.underline}](https://www.stickyminds.com/article/too-much-test-automation)
            interesting article

        2.  Test impact analysis: [[The Rise of Test Impact
            Analysis]{.underline}](https://martinfowler.com/articles/rise-test-impact-analysis.html)

9.  When to retire tests

[[When Should You Rewrite or Retire a Test \| Software Test Automation
(subject7.com)]{.underline}](https://www.subject7.com/when-should-you-rewrite-or-retire-a-test/)
