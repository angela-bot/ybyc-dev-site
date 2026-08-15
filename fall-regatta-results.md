---
permalink: fall-regatta-results.html
---

# Fall Regatta results archive

{% for result in regattaResults.fall %}- [{{ result.label }}]({{ result.url }})
{% endfor %}
