RETRIVE_FACULTY_MEMBERS = """
Your job is to retrive information of faculty members from a markdown file.
The markdown file will contain multiple faculty members.

A faculty member object can be defined as the following TypeScript interface:

```typescript
interface FaucultyMember {
    name: string;
    title?: string;  // the title of the faculty member, e.g. Professor, Associate Professor, Prof, Enginner, etc.
    profile_url?: string; // the url to the detailed profile of the faculty member
}
```

You must serialize every racultyMember object you find in the markdown file to a single line of json object, aka jsonl format,
and put them in a json block, for example:
```json
{"name":"Alice","title":"Associate Professor","profile_url":"https://example.org/alice"}
{"name":"Bob","title":"Professor","profile_url":"https://example.org/bob"}
```
Note that the data in example above is not real, you should replace them with the real data you find.
You should try to find as much information as possible for each faculty member, but if you can't find some information, just leave them empty.
""".strip()


SCHOLAR_OBJECT_SCHEMA = """
You job is to retrive information of a scholar from a markdown file.
The markdown file is a resume or profile of a scholar, which contains the following information.
You need to extract information from the markdown file and build a Scholar object from what you find.

The definition of the Scholar object is as follows:

```typescript
// The Experience interface represents the experience of a person,
// it can be a education experience, a work experience, a research experience, etc.
interface Experience {
    title: string;  // the title of the experience, e.g. Bachelor, Master, PhD, Postdoc, Professor, Engineer, etc.
    institute: string;  // the name of the institute, e.g. University of Washington, Google, Microsoft, etc.
    group?: string;  // the group of the experience, e.g. John's research group, Organic Chemistry Lab, etc.
    advisor?: string;  // the advisor or group leader of the experience, e.g. Prof. John Doe, Dr. Alice, etc.
    start_year?: number;  // the start year of the experience, e.g. 2010
    end_year?: number; // the end year of the experience, e.g. 2015
    description?: string;  // a brief description of the experience
}

// The Scholar interface represents a scholar, e.g. a professor, an engineer, etc.
interface Scholar {
    name: string;
    title?: string;  // current title of the scholar, e.g. Professor, Associate Professor, Prof, Enginner, etc.
    email?: string;
    goolge_scholar_url?: string; // the url to the google scholar profile of the scholar
    introduction?: string; // a brief introduction of the scholar
    research_domain: string;  // the research domain of the scholar, e.g. Machine Learning, Computer Vision, etc.
    experiences?: Experience[]; // a list of experiences
}
```

You must serialize the Scholar object you find to a json object and put it in a json block, for example:

```json
{"name":"Alice","title":"Associate Professor","email":"alice@example.com","experiences":[{"title":"PhD","institute":"University of Washington", "group":"John's reserach team","advisor":"John Doe","start_year":2010,"end_year":2015,"description":"..."}]}
```
Note that the data in example above is not real, you should replace them with the real data you find.
You should try to find as much information as possible, but if you can't find some information, just leave them empty.
""".strip()
