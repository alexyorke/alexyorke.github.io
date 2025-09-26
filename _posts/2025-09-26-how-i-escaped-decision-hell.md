---

title: "How I escaped decision hell by using a 1972 cognitive theory"
date: 2025-09-26
---

Making decisions is an inherent part of engineering. That might mean picking a database, a message queue, or a CSV library that will run in production against customer data. When several options are viable but trade-offs differ, you need a pragmatic way to narrow the field. The goal is to decide quickly, logically, and effectively.

One useful strategy is **Elimination by Aspects (EBA)**. This approach helps you narrow down options systematically until the choice becomes clear. The goal is to show how you can quickly get the “shape” of a problem, the rough contours of the solution space, without exhaustive analysis of every option.

## What is Elimination by Aspects?

Elimination by Aspects is a decision-making heuristic introduced by psychologist Amos Tversky in 1972. The core idea is to gradually whittle down a list of alternatives by applying one criterion (aspect) at a time. Then you move to the next criterion, and so on, until you’re left with a manageable shortlist or even a single winner. In other words, you filter options sequentially by your must-have requirements.

**Key characteristics of EBA:**

*   It’s an iterative, **non-compensatory** process. This means an option that fails one essential criterion is out, no matter how great it is on other factors.
*   You’re effectively making a series of **yes/no decisions** on each aspect, rather than comparing everything against everything at once.

### Example: Buying a Lawnmower with EBA

To illustrate the process, let’s use a non-software example first: buying a lawnmower.

1.  **Type of Mower:** Is it a ride-on, robotic, or push mower?
2.  **Yard Size:** How large is the area you need to mow?
3.  **Terrain:** Do you need to mow on steep slopes (15° or more)?
4.  **Power & Maintenance:** Do you prefer gas engine power or electric (battery/corded)? And how much maintenance are you okay with?
5.  **Budget Range:** What’s your budget ceiling?

By sequentially applying these aspects, you might cut the options down from thousands to a handful. Essentially, you ask the most consequential questions first (those that divide the field the most). EBA works best when you choose aspects that maximize information gain early in the process.

I found that ChatGPT Thinking/Pro, or Gemini 2.5 Pro (both with web search enabled) generated pretty good EBA-style questions, the prompt I used was “What are the top 5 questions to narrow down my lawnmower search?”.

### Example: Selecting a CSV Parser Library with EBA

Now let’s apply EBA to a software engineering decision. Suppose you need to choose a CSV parsing library for a project. Here’s how an elimination-by-aspects strategy might look:

1.  **Start with the Universe of Options:** Do a broad search filtered by your programming language to list all CSV parser libraries that could be relevant. This is your initial pool.
2.  **Suitability for Production:** Immediately discard any libraries that look obviously unsuitable for production use.
3.  **Basic Viability Check:** Apply a few must-have sanity criteria to the remaining list:
    *   **Compilation/Installation:** The library should at least compile/build or install cleanly.
    *   **Popularity/Community Usage:** While not a perfect metric, check if the library has at least a minimal level of adoption, for instance, a few hundred stars on GitHub or a decent number of weekly downloads on NPM/PyPI.
    *   **Documentation:** If there’s no README or documentation, that’s a huge red flag.
    *   **When was the package published, was it yesterday?** If it’s been out for a while, then there is more time for people to report the package being malicious, etc.
4.  **Feature and Performance Requirements:** With a shorter list in hand, introduce more specific criteria based on your project’s needs:
    *   **Performance:** Do you need to parse very large CSV files or do streaming?
    *   **Features:** Identify required features (e.g., does it handle quoted fields correctly? Can it parse into custom data types or handle different delimiters? Does it also support writing CSV, if you need that?).
    *   **Robustness:** Consider how the library handles malformed data or edge cases (like newline characters within fields, missing values, etc.).
    *   **Dependencies:** Does the library drag in huge external dependencies or native modules?
    *   **Maintenance:** Is the library actively maintained?
5.  **Final Selection:** By this point, you’ve likely narrowed it down to a handful (or even a single) candidate that meets all your aspects.

> I applied elimination by aspects to 200 npmjs libraries tagged with "csv" by attaching all 200 readmes to a Gemini 2.5 Pro chat, here is how I narrowed them down:

![EBA filtering diagram]({{ "/assets/images/eba_diagram.png" | relative_url }})

Further refinement for "server-side, not browser-based user downloads" reduced the choices to 30. This iterative process allowed for increasingly specific filtering based on desired functionality. You can select multiple branches in parallel as well if you’re unsure which direction to take or skip questions.

If you're not willing to download 200 readmes (I don't blame you), the prompt I used for Gemini was "use elimination by aspects questions to tell me which library I should use based on my answers to your questions to select a csv parser library on npmjs.org." and then it interviewed me and chose a library for me based on my answers.

## Benefits of Using EBA in Tech Decisions

Employing elimination-by-aspects in software engineering decisions offers several benefits:

*   **Reduces Overwhelm:** By focusing on one criterion at a time, you avoid the mental burnout of weighing every factor of every option simultaneously.
*   **Ensures Must-Haves Are Met:** EBA forces you to identify and prioritize your non-negotiable requirements up front.
*   **Transparent and Defensible Process:** The step-by-step nature of EBA makes your decision process transparent.
*   **Reduces Bias, Promotes Objectivity:** Deciding on criteria before getting enamored with a particular option can mitigate knee-jerk bias toward a familiar or “shiny new” technology.

## Caveats and Limitations to Watch For

No decision technique is perfect. Keep these caveats in mind when using elimination by aspects:

*   **Non-Compensatory = No Trade-Offs:** Because EBA is non-compensatory, an otherwise great option will get tossed out if it fails on one chosen criterion. *Tip: Choose your elimination aspects carefully and make sure each one really is a deal-breaker.*
*   **Order Matters:** The sequence in which you apply criteria can affect the outcome. It’s usually wise to start with the highest priority aspect, essentially, assert “if it doesn’t have X, nothing else matters” only for truly fundamental X’s.
*   **Requires Clear, Measurable Criteria:** EBA works best when your aspects are well-defined. For instance, define scalability as “must handle >10k requests/sec” or security as “must have no critical vuln reports in the last year”, whatever fits your context.
*   **May Not Yield a Unique Winner:** Sometimes you’ll go through your list of aspects and still end up with a tie or a few viable candidates. If multiple options survive all your filters, you can then switch to comparing them on secondary attributes or even doing a proof-of-concept with each.

## Wrapping Up

Elimination by aspects is a handy tool in the decision-making toolbox for software engineers. Whenever you’re faced with a daunting list of technologies or design choices, think in terms of aspects: figure out your must-haves, and start chopping off options that don’t check those boxes.

In the fast-moving tech world, where new libraries and frameworks pop up weekly, this approach can help you and your team avoid analysis paralysis and make decisions with confidence.

Ultimately, elimination by aspects won’t guarantee a perfect choice (no method can), but it will give you a rational, repeatable process to arrive at a good choice that meets your needs. It provides practicality and efficiency in decision-making, even if it may not lead to the absolute optimal outcome in hindsight.