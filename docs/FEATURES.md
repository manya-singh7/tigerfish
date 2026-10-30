# TigerFish features: where each one lives

Nothing gets buried (docs/DESIGN.md): every feature is reachable in at most three clicks
from Home and has a visible entry point in the top menu, a report's tabs or the sections
under its Findings tab.

`scripts/check_design.py` reads the **Entry point** column and fails if any entry is not
visible. Its steps, separated by ` · `, are followed from Home in order:

- `menu=<name>`: click that top-menu item (1 click).
- `report=<id>`: click that report's row on Home (full audits), or "Open report" on its row
  in the Library (1 click).
- `tab=<name>`: click that tab of the open report (1 click).
- `section=<name>`: pick that section under the Findings tab (1 click).
- `text=<text>`: the text must then be visible (no further click), or
  `css=<selector>`: an element matching it must be visible.

| Feature | Where it lives | Entry point |
|---|---|---|
| Contradictions | Report, Findings, Contradictions | report=great_nicobar_2021_draft · tab=Findings · section=Contradictions · text=Internal contradiction |
| Recycled figures | Report, Findings, Contradictions (Check filter; "What this check does") | report=great_nicobar_2021_draft · tab=Findings · section=Contradictions · text=recycled figures |
| Evidence slips with page crops | Home, every flag list | report=great_nicobar_2021_draft · tab=Findings · section=Contradictions · css=.tf-slip-crop img |
| Model badges (which model read, judged, verified) | Every finding slip | report=great_nicobar_2021_draft · tab=Findings · section=Contradictions · css=.tf-model |
| Human review: Confirm, Dismiss, Unsure | Every finding slip | report=great_nicobar_2021_draft · tab=Findings · section=Contradictions · text=Confirm |
| Investigate agent with traces | Every finding slip (button, or the recorded investigation) | report=great_nicobar_2021_draft · tab=Findings · section=Contradictions · text=Investigat |
| Species out of range | Report, Findings, Species & nature | report=great_nicobar_2021_draft · tab=Findings · section=Species & nature · text=Species out of range |
| Species map | Report, Findings, Species & nature | report=great_nicobar_2021_draft · tab=Findings · section=Species & nature · text=Where the flagged species are actually recorded |
| Species photos | Report, Findings, Species & nature | report=indira_point_table_3_16 · tab=Findings · section=Species & nature · css=.tf-photo img |
| Omissions (threatened species never mentioned) | Report, Findings, Species & nature | report=great_nicobar_2021_draft · tab=Findings · section=Species & nature · text=omissions |
| IUCN and WPA status | Report, Findings, Species & nature | report=indira_point_table_3_16 · tab=Findings · section=Species & nature · text=IUCN category |
| Knowable at the time | Finding slips (Species & nature, Contradictions) | report=indira_point_table_3_16 · tab=Findings · section=Species & nature · css=.tf-knowable |
| Consultant accreditation (NABET) | Report, Findings, Public record | report=great_nicobar_2021_draft · tab=Findings · section=Public record · text=accreditation |
| Copied text | Report, Findings, Copied text | report=great_nicobar_2021_draft · tab=Findings · section=Copied text · text=Copied text |
| ToR promises, granted and proposed | Report, Findings, Promises & timeline | report=great_nicobar_2021_draft · tab=Findings · section=Promises & timeline · text=Granted ToR (MoEFCC letter |
| Survey timeline | Report, Findings, Promises & timeline | report=great_nicobar_2021_draft · tab=Findings · section=Promises & timeline · text=Proposed ToR ( |
| Official record check | Report, Findings, Public record | report=great_nicobar_2021_draft · tab=Findings · section=Public record · text=Does it match the official record? |
| Public record: what happened next | Report, Findings, Public record | report=great_nicobar_2021_draft · tab=Findings · section=Public record · text=What happened next |
| Paper trail: documents found | Report, Findings, Public record | report=great_nicobar_2021_draft · tab=Findings · section=Public record · text=Documents found |
| Authority contacts (who to write to) | Report, Findings, Public record | report=great_nicobar_2021_draft · tab=Findings · section=Public record · text=Who to write to |
| Evidence from the web | Report, Findings, Public record (expander) | report=great_nicobar_2021_draft · tab=Findings · section=Public record · text=Evidence from the web |
| Reviewer's memo | Report, Ask & investigate tab | report=great_nicobar_2021_draft · tab=Ask & investigate · text=Reviewer's memo |
| Ask the report | Report, Ask & investigate tab | report=great_nicobar_2021_draft · tab=Ask & investigate · text=Ask the report |
| Objection letter (English, Hindi; Tamil or Kannada for those states) | Report, Take action tab | report=great_nicobar_2021_draft · tab=Take action · text=Letter language |
| Tamil letter | Report, Take action tab (Tamil Nadu reports) | report=cuddalore_port_2026_draft · tab=Take action · text=Tamil |
| RTI and public hearing pack | Report, Take action tab | report=great_nicobar_2021_draft · tab=Take action · text=RTI + public hearing pack (.zip) |
| Review queue | Report, Method & quality (Quality) | report=great_nicobar_2021_draft · tab=Method & quality · text=Every new RED/ORANGE flag |
| Precision | Report, Method & quality (Quality) | report=great_nicobar_2021_draft · tab=Method & quality · text=Precision |
| Evaluation | Report, Method & quality (Quality) | report=great_nicobar_2021_draft · tab=Method & quality · text=Evaluation |
| Cost card | Report, Method & quality (Cost & models) | report=great_nicobar_2021_draft · tab=Method & quality · text=Cost per full audit, by triage mode |
| Context efficiency | Report, Method & quality (Cost & models) | report=great_nicobar_2021_draft · tab=Method & quality · text=Context efficiency |
| Super-VL scanned-page inspector | Report, Method & quality (Cost & models) | report=great_nicobar_2021_draft · tab=Method & quality · text=How TigerFish reads scanned pages |
| Report library with live totals | Library | menu=Library · css=.tf-lib-total |
| Batch check summary and report links | Library, Batch screening results expander | menu=Library · text=Batch screening results |
| Batch certificate, baseline and species evidence | Quick report, Batch screening tab | menu=Library · report=3a84436e0e972dbf · tab=Batch screening · text=Certificate-date screen |
| Library search | Library, the filters above the list | menu=Library · text=Search by project name |
| Library filters: State, Sector, Year, Audit type radio | Library, the filters above the list | menu=Library · text=Audit type |
| Filter: Has RED flags | Library, the filters above the list | menu=Library · text=Has RED flags |
| Filter: Has human-verified findings | Library, the filters above the list | menu=Library · text=Has human-verified findings |
| Upload with three levels | Top menu, Upload | menu=Upload · text=Chosen pages, live. |
| Page picks for the deep audit | Upload page (after a PDF is read) | menu=Upload · text=pages you choose |
| How it works (diagram, levels, models) | Top menu, How it works | menu=How it works · text=Three levels |
| Limitations | Top menu, Limitations | menu=Limitations · text=Every flag is a lead, not a verdict. |
