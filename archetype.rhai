let context = #{};

// Pass `-s debug-answers` to archetect to output the answers it sees from various sources
if switch_enabled("debug-answers") {
    log(Info, archetect::archetype::description() +" Answers:");
    display(as_yaml(ANSWERS));
}

// Use the same switches, defaults, etc passed to this archetype, and pass them to the next
let render_settings = archetect::archetype::settings();

context += render(Archetype("data-prompts"), ANSWERS, render_settings);

context += prompt("Project Prefix:", "project-prefix", #{
    placeholder: "edgar",
    cases: [
        CasedIdentityCasedValue(PROGRAMMING_CASES),
    ],
});

context += set("project-name", render("{{ project-prefix }}-{{ org-name }}-{{ venture-name }}", context), #{
    cases: [
        CasedIdentityCasedValue(PROGRAMMING_CASES),
        FixedKeyCasedValue("project-title", TitleCase),
    ],
});

context += prompt("Project Author:", "author_full", #{
    placeholder: "Your Name <your.name@example.com>",
});

context += prompt("Packages:", "packages", #{
    defaults_with: ["edgar"],
    type: List,
    cases: [
        CasedKeyCasedValue("package-name", PROGRAMMING_CASES),
        FixedKeyCasedValue("package-title", TitleCase),
    ],
});

context += prompt("Features:", "features", #{
    type: MultiSelect([
      "edgar",
    ]),
});


// Pass `-s debug-context` to archetect to output the context 
if switch_enabled("debug-context") {
    print("Context:");
    print(as_yaml(context));
    print();
}

context["github-artifactory_username"] = "${{ secrets.ARTIFACTORY_USERNAME }}";
context["github-artifactory_id_token"] = "${{ secrets.ARTIFACTORY_IDENTITY_TOKEN }}";

render(Directory("contents/base"), context);

for item in context.packages {
    render(Directory("contents/package"), context + item);
}


context

