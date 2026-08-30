# MONAD IO Issues

This is the working brief for revising Part 3. It answers two questions: what readers in the sampled material find confusing, frustrating, or misleading about IO and Monad tutorials, and which of those problems actually occur in the current C# article.

The latest review changes the earlier diagnosis in one important way: **Part 3 does not need a structural rewrite.** Its main teaching path is already strong. The serious problems are concentrated in a few passages about evaluation order, referential transparency, deferral, and composition. Those passages should be replaced, while the implementation, workflow, execution boundary, laws, and conclusion structure should remain in place.

The evidence combines ten tutorial audits; official Haskell, C#, and library documentation; Hacker News submissions and related threads found in searches run August 23, 2026; selected discussions on Reddit, Lobsters, Stack Overflow, and language forums; and a YouTube comment corpus. A separate ten-agent source-verification pass followed on August 29. The final adversarial review used two mirrored teams of ten: nine isolated specialists argued for revision, nine isolated specialists argued for preservation, and one liaison on each side exchanged the teams' challenges. Neither team edited the article or this report. Both liaisons reached the same conclusion: preserve the architecture and make localized correctness repairs.

This is a bounded exploratory review, not a prevalence study. Community reactions show real examples of reported friction, but they do not establish how common a problem is or settle technical questions. Primary documentation remains the authority for semantics.

The supplied YouTube workbook is also a convenience sample. Its 699 data rows contained 651 YouTube URLs and 371 unique video IDs, including 280 duplicate URL rows. Unauthenticated `yt-dlp` collection recovered metadata for 365 videos; 175 files contained comments, totaling 10,715 unique comments and replies. Six IDs lacked metadata, and inaccessible, deleted, hidden, or incompletely retrieved comments are absent. A rule-based screen labeled 198 videos programming- or effect-related, not necessarily IO-specific. Seventy-two had retrieved comments, yielding 7,274 comments; broad English-keyword and question-mark rules flagged 2,075 candidates for manual inspection. The labels overlap and cannot rank actual learner confusion. Five popular videos supplied 68.1% of the analysis comments and 70.7% of the candidates. The linked examples below were manually matched to their cached IDs, text, and collection-time likes.

## What readers find confusing, and how Part 3 currently fares

The research produced twelve recurring concerns. The adversarial review found that only a subset applies strongly to Part 3:

| # | Tutorial problem | Part 3 verdict | Decision |
| --- | --- | --- | --- |
| 1 | The practical payoff arrives after the abstraction | Applies partly | Preview the C# payoff earlier, but keep the full workflow after the implementation. |
| 2 | Too many prerequisites are introduced together | Applies partly | State the Parts 1 and 2 prerequisite and reduce Haskell to one short bridge. |
| 3 | Monad, IO, and effects are treated as synonyms | Local but severe | Replace the current composition subsection. |
| 4 | Deferral is confused with sequencing and execution | Local but severe | Give `Delay`, `FlatMap`, and `UnsafeRun()` separate jobs. |
| 5 | `Map` and `FlatMap` are not motivated by their types | Applies partly | Add one compact `IO<IO<T>>` versus `IO<T>` contrast. |
| 6 | Metaphors become false definitions | One local defect | Keep "recipe" once; delete "list of instructions." |
| 7 | Pure evaluation, IO action order, and statement order are conflated | Local but severe | Scope the comparison to Haskell and C# and delete the `Debug.Trace` example. |
| 8 | Referential transparency is taught with invalid substitutions | Applies strongly | Delete the file/string and algebra examples; use one stored result versus two calls. |
| 9 | Construction, execution, and reruns remain blurry | Several local defects | Correct validation, coldness, continuation, and repeatability wording. |
| 10 | The C# value proposition is exaggerated or dismissed | Early framing needs balance | Describe a voluntary visible boundary, not repaired language semantics. |
| 11 | IO is equated with `Task`, async, or scheduling | Does not currently apply | Add one synchronous caller-thread sentence; do not add an async section. |
| 12 | Failure, resources, and toy-runtime limits are omitted | Partly covered | Preserve the exception discussion and add one compact limitations paragraph. |

### Motivation, payoff, and prerequisites

Readers repeatedly ask what IO buys them over ordinary code. A detailed [response to "Don't fear the Monad"](https://www.youtube.com/watch?v=ZhuHCtR3xq8&lc=UghZWwN6QT8ZxXgCoAEC) recommends beginning with a familiar problem and ordinary solution before introducing the abstraction. A [Computerphile response](https://www.youtube.com/watch?v=t1e8gqXLbsU&lc=UgyUC32QOVtZXao6_Uh4AaABAg) makes the related point that following one example is not enough if the mechanism does not transfer to another problem. These are individual comments, not survey results, but they identify a useful teaching test.

Part 3 already performs better than many tutorials on this dimension. It starts with familiar C# effects, shows direct procedural code, supplies a complete workflow, and places the laws late. Parts 1 and 2 have already introduced `Map` and `FlatMap`. The article therefore does not need a new opening example or an earlier copy of the full workflow.

The remaining problem is pacing. A long Haskell and referential-transparency detour separates the procedural baseline from the concrete C# payoff. The fix is a short prerequisite sentence and an early preview of the payoff: ordinary C# already orders direct calls, while `IO<T>` makes an intended deferred boundary visible in a return type and lets application code choose where to run the composed workflow.

This conclusion is narrower than the earlier recommendation to rebuild the teaching sequence. Both adversarial teams rejected moving the complete workflow ahead of the class. That move would require unexplained APIs or duplicate the article's strongest example.

### Monad, IO, deferral, and dependent composition

A monad is not a synonym for IO or side effects. At the level used in this series, it is a type constructor with lifting and binding operations expected to satisfy the monad laws. `List`, `Maybe`, `Result`, parsers, and state can have that shape without performing external IO. The [Haskell 2010 `Monad` class](https://www.haskell.org/onlinereport/haskell2010/haskellch13.html) defines `return` and `(>>=)` and states the expected laws; each concrete instance supplies its own operational meaning.

Part 3 mostly respects this distinction, but its current central composition subsection does not. It says that deferred IO composes "with other monads," describes `Map` as responsible for sequencing IO, suggests that a main runtime automatically executes a returned value, and calls the result a list of instructions. None of those claims matches the delegate-backed type in the article:

- `Delay` stores a delegate without invoking its body. That is deferral.
- `FlatMap` runs the source during execution, supplies its result to a continuation, and then runs the IO returned or selected by that continuation. That is dependent sequencing for this IO type.
- `UnsafeRun()` invokes the stored computation. That is the execution boundary.

Deferral is necessary for this style of composition, but it does not itself decide whether work runs zero, one, or many times. A stored `Func<T>` already postpones its body; the program's calls to `UnsafeRun()` determine whether attempts begin, and the nested delegates created by `FlatMap` determine the dependency order within an attempt.

The missing type-level motivation is small but important. If a function `Order -> IO<decimal>` is mapped over an `IO<Order>`, ordinary `Map` produces `IO<IO<decimal>>`. `FlatMap` produces `IO<decimal>` by composing the result-dependent next IO without running either operation at composition time. This is why bind is needed; "unwrapping a box" does not explain it.

The broad YouTube regex tagged 325 candidates with words related to `Map`, `FlatMap`, bind, or `Pure`, but 124 matched only ambiguous words such as "map," "return," "join," or "lift." The count cannot measure prevalence. It does, however, contain concrete examples: one [viewer lost the talk at bind](https://www.youtube.com/watch?v=ZhuHCtR3xq8&lc=UgiPO-zI498wd3gCoAEC), while another said the signature made sense but the [examples needed to come first](https://www.youtube.com/watch?v=ZhuHCtR3xq8&lc=UghmoJ-D6AWD0HgCoAEC).

Related Hacker News threads contain both [a debate over whether monads force sequencing](https://news.ycombinator.com/item?id=16419877) and [disagreement about what problem monads solve](https://news.ycombinator.com/item?id=17645277). They are useful examples of the distinction readers dispute, not semantic authorities or evidence of a community consensus.

### Metaphors

"Recipe" is useful once for distinguishing construction from execution. It should not become the definition. A recipe can obscure dynamic dependencies, failure, and repeated execution, while "box containing a `T`" implies that a completed result is already available.

The article does not have an article-wide metaphor problem. It does not rely on a literal world snapshot, taint model, or box definition. The only definite error is "list of instructions": this implementation stores opaque nested delegates, not an inspectable syntax tree. Keep the brief recipe intuition, then use "deferred computation" and describe the stored delegate directly.

This is consistent with the community evidence. [One commenter in a generally positive Reddit discussion](https://www.reddit.com/r/haskell/comments/gfqzjb/comment/fpvy34y/) said that special "action" and "box" language was a major source of confusion. [One Lobsters commenter](https://lobste.rs/s/0l1bcm/understanding_monads) argued that definitions alone can leave operational questions unanswered. Neither comment supports purging every metaphor; both support grounding the metaphor in behavior and types.

### Evaluation order and referential transparency

This is the article's most serious correctness cluster.

[Haskell 2010 is non-strict](https://www.haskell.org/onlinereport/haskell2010/haskellch1.html): a pure expression need not be evaluated in source order, and an unused expression need not be evaluated. IO actions composed with bind have an encoded action order. These facts are related, but they are not the same claim. The [Haskell IO chapter](https://www.haskell.org/onlinereport/haskell2010/haskellch7.html) and [translation of `do` notation](https://www.haskell.org/onlinereport/haskell2010/haskellch3.html#x8-470003.14) provide the relevant language-level account.

C# is different. For the direct code in Part 3, local initializer statements are reached in order, and C# evaluates a call's receiver and then its argument expressions in textual left-to-right order. Short-circuiting constructs can skip an operand, and an implementation can optimize only within the specification's observable-behavior constraints. See the C# specifications for [expressions](https://learn.microsoft.com/en-us/dotnet/csharp/language-reference/language-specification/expressions) and [execution order](https://learn.microsoft.com/en-us/dotnet/csharp/language-reference/language-specification/basic-concepts#710-execution-order). The toy IO type is not repairing C# evaluation rules; it borrows the separation between describing and running work.

The current `Debug.Trace.trace` demonstration should be removed. [`trace`](https://ghc.gitlab.haskell.org/ghc/doc/libraries/base-4.22.0.0-inplace/Debug-Trace.html) is a pure-typed debugging escape hatch implemented through unsafe machinery, not an IO action or a referentially transparent observation. It writes to stderr while `print` writes to stdout, so one displayed merged output is not a portable guarantee. A short accurate paragraph is clearer than the example.

The current referential-transparency examples are also invalid:

- Once C# evaluates `var x = ReadFile(...)`, `x` is the returned value. Reading `x` again does not rerun `ReadFile`.
- The sample says the file calls return strings, so `x + y` concatenates and `2 * x` does not compile.
- Even for numbers, replacing `x + y` with `2 * x` is valid only if `x == y`.
- In algebra, a variable denotes a value. Claiming that two occurrences of `x` can independently change teaches the opposite of referential transparency.

The correct C# contrast is a stored result versus repeated effectful calls:

```csharp
int counter = 0;
int Next() => ++counter;

int x = Next();
int reused = x + x;                // 2: one call

counter = 0;
int repeated = Next() + Next();    // 3: two calls
```

`x + x` reuses one value. `Next() + Next()` performs two observable calls. That establishes why direct effectful calls cannot be freely duplicated or rearranged without confusing values with actions.

In ordinary safe Haskell, a pure expression denoting an IO action remains referentially transparent. Reusing the action value is not the same as reusing its eventual result: sequencing the action twice performs it twice, whereas reusing a result bound with `<-` does not rerun the action. Part 3 does not need this full distinction in the main text, but it must not imply the opposite.

### Lifecycle and the value of the C# type

Readers need distinct answers for construction, composition, first execution, and repeated execution:

- `Pure(EffectfulCall())` is eager because C# evaluates the argument before calling `Pure`.
- `Delay(() => EffectfulCall())` stores a delegate whose body has not run.
- `Map` and `FlatMap` build new delegates; their callbacks run when the composed computation runs.
- Each `UnsafeRun()` invokes the wrapper's stored delegate again. The wrapper adds no memoization.

"Cold" should mean only that construction and composition do not invoke the stored delegate bodies. C# still evaluates receivers and arguments immediately. Null checks, allocations, exceptions, and effects performed by surrounding caller code can occur during construction. The `Func` types cannot enforce purity.

Several current phrases need that precision. `FetchCurrentPriceIO` does not validate `remotePriceApi` or `productId`; the prose should drop the claim rather than change the teaching API's behavior. A continuation returns or selects the next IO; it need not construct a fresh one. A second `UnsafeRun()` attempts the workflow again, but an earlier failure can prevent later steps, and a captured operation can cache internally, be one-shot, or return a different result.

This also gives the balanced C# value proposition. Ordinary C# already orders direct calls. `IO<T>` supplies a voluntary convention: it makes an intended deferred boundary visible, lets mostly pure application logic compose dependent work, and gives the outer caller an explicit place to start it. It does not prove purity, prevent eager effects, make the opaque delegates inspectable as data, add rollback, or turn a network request into mathematics.

Forum discussions about IO in [C#](https://stackoverflow.com/questions/21364837/does-an-io-monad-make-sense-in-a-language-like-c-sharp) and [OCaml](https://discuss.ocaml.org/t/io-monad-for-ocaml/4618) show the same tradeoff between an explicit effect boundary and voluntary discipline or ceremony. The strongest positive C# design in the linked discussion uses an inspectable operation tree and multiple interpreters. Those benefits do not transfer to Part 3's opaque `Func<T>` wrapper.

The current article already contains the right boundary and exception model: application code calls `UnsafeRun()`, a thrown exception prevents later steps, and earlier effects are not rolled back. The final version only needs one compact limitation: `UnsafeRun()` synchronously invokes the stored delegate on the caller's thread and adds no asynchronous behavior. Owned resource acquisition, use, and disposal should stay in one delayed scope, using [`using`](https://learn.microsoft.com/en-us/dotnet/csharp/language-reference/statements/using) or `try/finally`. The wrapper provides no scheduler, cancellation, memoization, or thread-safety guarantee and no trampoline for arbitrarily deep `Map` or `FlatMap` chains.

There is no reason to add an `IO<Task<T>>` discussion. Part 3 does not introduce that type, and the existing conclusion already says the example is not a replacement for the Task-based Asynchronous Pattern. Microsoft's [TAP guidance](https://learn.microsoft.com/en-us/dotnet/standard/asynchronous-programming-patterns/task-based-asynchronous-pattern-tap) is useful verification, not material the tutorial must teach.

### Overall diagnosis

The sampled sources suggest a common failure pattern: delay the practical problem, introduce several abstractions at once, let a metaphor replace operational behavior, leave bind and execution timing unexplained, and then overstate claims about purity or sequencing. The positive pattern reverses that order: familiar behavior, visible types, a concrete nesting problem, `FlatMap` as its repair, a composed program, an explicit run, and only then the Monad name and laws. Viewers praised a [part-to-whole progression](https://www.youtube.com/watch?v=C2w45qRc3aU&lc=UgxVX3z9IZyyMg4hCwd4AaABAg), a [concise developer-oriented explanation](https://www.youtube.com/watch?v=VgA4wCaxp-Q&lc=UgzuHIU2VIAALcoytep4AaABAg), and an [IO-specific explanation](https://www.youtube.com/watch?v=fCoQb-zqYDI&lc=UgztPYFbrjqW7VrKEiN4AaABAg).

Part 3 already has most of the positive pattern. Its procedural baseline, minimal implementation, adjacent before-and-after workflows, dependency diagram, explicit run boundary, and late law section are strengths. The report should therefore guide a concentrated repair, not encourage expanding the article into a survey of functional effects.

## How to fix Part 3

### Decision boundary

Preserve the article's current architecture:

- title and description;
- familiar effect definition and procedural append example;
- minimal `Unit` and `IO<T>` implementation;
- procedural and composed workflows beside each other;
- dependency-order diagram;
- explicit `UnsafeRun()` application boundary;
- laws after the behavior is visible;
- concrete conclusion and exercise.

Do not move the complete workflow before the class. Do not add new combinators, category theory, higher-kinded abstractions, an AST or alternate interpreter, an async detour, or a production-library comparison. These additions would answer questions the article does not ask and recreate the prerequisite overload identified in the research.

### Must change

#### 1. Preview the payoff and state the prerequisite

Add a compact gate near the opening:

> This part assumes the `Map` and `FlatMap` distinction from Parts 1 and 2; no Haskell syntax or category theory is required.

Then state the C# payoff without implying that the language's execution order is defective:

> Ordinary C# already orders these direct calls. The benefit here is organizational: `IO<T>` makes an intended deferred boundary visible in the return type, `FlatMap` composes a result-dependent next IO, and application code chooses where to run the completed workflow.

This is a preview, not a second explanation of the complete workflow.

#### 2. Replace the evaluation detour

Keep the procedural example. Replace the broad "functional programming changes the execution model" claim, the "procedural programming behaves differently" claim, and the `Debug.Trace` block with one short bridge:

> Pure expressions support substitution without changing observable behavior. Evaluation strategy is a separate question. Haskell is non-strict, so an unused pure binding may never be demanded; IO actions composed with bind nevertheless have an encoded action order. C# eagerly evaluates these local initializers as control reaches them. This tiny type borrows the description-versus-execution boundary rather than repairing C# evaluation order.

Delete the file-read substitution and `a != z` algebra blocks. If a concrete referential-transparency example remains, use the counter example above and explain only that a stored result is not the same as two calls.

#### 3. Replace the defective composition subsection

Replace the current subsection beginning with "Why does deferring IO make it composable and sequencable?" with this progression:

> `Delay` stores an operation without invoking it. That makes the work a value, but it does not decide its order or how many times it runs.
>
> If a function returning `IO<decimal>` is mapped over an `IO<Order>`, ordinary `Map` produces `IO<IO<decimal>>`. `FlatMap` avoids that nesting: when the composed computation is run, it runs the source, passes the result to the continuation, and then runs the IO returned or selected by that continuation.
>
> This composes IO with IO, not IO automatically with `List`, `Result`, or `Task`. Nothing executes merely because the value is returned. Application code starts the completed computation with `UnsafeRun()`.

Use this distinction consistently:

| Operation | Job |
| --- | --- |
| `Delay` | Defer a delegate body. |
| `Map` | Transform the eventual result with an ordinary function. |
| `FlatMap` | Compose a result-dependent function returning another IO. |
| `UnsafeRun()` | Invoke the stored computation. |

Delete the current `list.Map(...).FlatMap(...)` fragment, arbitrary-monad claim, claim that `Map` performs dependent sequencing, automatic-main-runtime story, and "list of instructions" description.

Also correct the series recap. `Map` transformed contextual values in the earlier articles; `FlatMap` or `Bind` composed steps whose next computation depended on an earlier result. They should not both be described as dependent composition.

#### 4. Correct lifecycle wording

Make the following surgical replacements:

| Current idea | Replacement |
| --- | --- |
| `FetchCurrentPriceIO` validates its arguments | Remove the claim. The shown helper only stores the request-producing lambda. |
| `Pure` can defer an effectful call | Show or state that `Pure(EffectfulCall())` is eager; use `Delay(() => EffectfulCall())` for deferral. |
| Construction performs no effects | Construction and composition do not invoke the stored file or network operations. Surrounding C# evaluation can still run, throw, allocate, or perform effects. |
| A continuation constructs the next IO | A continuation returns or selects the next IO. |
| Every run repeats the workflow | Every run attempts the workflow by invoking the stored delegate again; the wrapper adds no memoization. |
| The result is replayable | The wrapper is rerunnable or re-invocable; identical outcomes are not guaranteed. |
| The main program runs returned IO automatically | Application code explicitly calls `UnsafeRun()` at a boundary such as `Main`, a request handler, or a background-worker entry point. |

Correct the nearby spelling errors `familar`, `occured`, `disasterous`, and `sequencable` while editing those passages.

#### 5. State the runtime boundary once

Keep the current exception paragraph. Add one compact limitation near it or in the conclusion:

> `UnsafeRun()` synchronously invokes the stored delegate on the caller's thread and adds no asynchronous behavior. Keep acquisition, use, and disposal of resources owned by the workflow inside the same delayed scope. This wrapper supplies no scheduler, cancellation, memoization, or thread-safety guarantees, and deeply nested `Map` or `FlatMap` chains may overflow the stack because it has no trampoline.

Do not add `IO<Task<T>>`, Cats Effect, ZIO, or LanguageExt to the article. Those systems have different semantics and much larger scopes; naming them would not clarify this implementation.

### Should change

#### Make the laws precise without expanding them

Keep all three laws and their current late placement. Tighten the caveat to say what equality means for this executable type:

> Interpret equality observationally for freshly constructed programs: from equivalent starting state, both sides should have the same termination behavior and relevant effects in the same order and, when they terminate, the same result or equivalent failure. `f` and `g` must be deterministic, total, nonthrowing constructors of non-null IO values. They must not read mutable or external state, perform effects, call `UnsafeRun()`, or force returned IO values while constructing them. If the comparison includes rerunning the same wrapper, repeated continuation construction must also produce rerun-equivalent computations without fresh hidden mutable state. Ignore wrapper reference identity and limit the claim to this interpreter's operational bounds.

An exception thrown by a stored IO operation is an outcome to compare, not automatically a law violation.

#### Make the counter exercise test transfer

Keep the current counter exercise, but ask the reader to predict the counter after construction, after adding `Map`, after adding `FlatMap`, after the first `UnsafeRun()`, and after a second run. Also ask why `Pure(Next())` is eager while `Delay(() => Next())` is deferred, and what happens to later steps if one delayed operation throws. This checks the lifecycle model instead of merely asking the reader to reproduce the class.

### Preserve

- The familiar definition of an effect and pure/effectful contrast.
- The procedural append example.
- The remote-price helper returning `IO<decimal>`.
- The complete `Unit`, `Pure`, `Delay`, `Map`, `FlatMap`, and `UnsafeRun()` implementation.
- The adjacent direct and composed workflows.
- The dependency diagram.
- The explicit execution boundary, normal exception propagation, laws, conclusion structure, and exercise.
- "Recipe" once as bounded intuition, followed by "deferred computation."

### Omit

- Relocating or duplicating the full workflow.
- New combinators or API behavior.
- A wholesale metaphor purge.
- `IO<Task<T>>` and an async tutorial.
- ASTs, alternate interpreters, or effect-coloring theory.
- Category theory, generic higher-kinded abstractions, or transformers.
- A Cats Effect, ZIO, or LanguageExt feature survey.
- Claims that this opaque delegate wrapper is inspectable program data or a production effect runtime.

### Exact terminology

| Avoid | Use instead |
| --- | --- |
| "`IO<T>` contains a `T`." | "`IO<T>` is a deferred computation that may perform effects and produce a `T` when run." |
| "IO makes an impure function pure." | "Pure code can construct and combine deferred effectful work; running it still performs effects." |
| "Deferral sequences effects." | "Deferral stores work; this `FlatMap` implementation encodes a result-dependent next IO." |
| "Monad forces evaluation order." | "When this IO is run, its delegates are invoked in the dependency order encoded by its `FlatMap` chain." |
| "Bind unwraps IO." | "`FlatMap` passes the result to a continuation that returns or selects the next IO." |
| "The IO runs exactly once." | "It may be run zero, one, or many times; each `UnsafeRun()` invokes the wrapper's stored delegate." |
| "Cold construction has no effects." | "Cold means construction and composition do not invoke the stored delegate bodies." |
| "The main program runs it for you." | "Application code explicitly calls `UnsafeRun()` at an application boundary." |
| "List of instructions." | "Opaque deferred computation." |
| "The immutable IO is thread-safe." | "The wrapper is immutable; captured operations and state may not be thread-safe." |

### Definition of done

- The article answers "why use this in C#?" before implementation details without duplicating the full workflow.
- Every behavioral claim is local to the delegate-backed synchronous `IO<T>` unless Haskell is named explicitly.
- No variable is described as rerunning the operation that initialized it.
- Construction, composition, first execution, and repeated execution are observably distinct.
- `Delay`, `Map`, `FlatMap`, and `UnsafeRun()` each have one consistent role.
- Haskell syntax and category theory are not prerequisites for the C# explanation.
- The end-to-end workflow remains the center of the article.
- Failure, resource lifetime, and runtime limitations are stated once.
- The conclusion gives one application rule: construct effects with `Delay`, transform eventual values with `Map`, compose dependent IO with `FlatMap`, and call `UnsafeRun()` at the application boundary.
