# TigerFish features: where each one lives

Nothing gets buried (docs/DESIGN.md): every feature is reachable in at most two clicks from
Home and has a visible entry point in the top menu, a report's section tabs or a side panel.

`scripts/check_design.py` reads the **Entry point** column and fails if any entry is not
visible. Its steps, separated by ` · `, are followed from Home in order:

- `menu=<name>`: click that top-menu item (1 click).
- `report=<id>`: click "Open report" on that report's card in the library on Home (1 click).
- `tab=<name>`: click that section tab of the open report (1 click).
- `text=<text>`: the text must then be visible (no further click), or
  `css=<selector>`: an element matching it must be visible.

| Feature | Where it lives | Entry point |
|---|---|---|
| Contradictions | Report, Contradictions tab | report=great_nicobar_2021_draft · tab=Contradictions · text=Internal contradiction |
| Recycled figures | Report, Contradictions tab (Check filter; "What this check does") | report=great_nicobar_2021_draft · tab=Contradictions · text=recycled figures |
| Evidence slips with page crops | Home, library cards, every flag list | report=great_nicobar_2021_draft · tab=Contradictions · css=.tf-slip-crop img |
| Model badges (which model read, judged, verified) | Every finding slip | report=great_nicobar_2021_draft · tab=Contradictions · css=.tf-model |
| Human review: Confirm, Dismiss, Unsure | Every finding slip | report=great_nicobar_2021_draft · tab=Contradictions · text=Confirm |
| Investigate agent with traces | Every finding slip (button, or the recorded investigation) | report=great_nicobar_2021_draft · tab=Contradictions · text=Investigat |
| Species out of range | Report, Species & nature tab | report=great_nicobar_2021_draft · tab=Species & nature · text=Species out of range |
| Species map | Report, Species & nature tab | report=great_nicobar_2021_draft · tab=Species & nature · text=Where the flagged species are actually recorded |
| Species photos | Report, Species & nature tab | report=indira_point_table_3_16 · tab=Species & nature · css=.tf-photo img |
| Omissions (threatened species never mentioned) | Report, Species & nature tab | report=great_nicobar_2021_draft · tab=Species & nature · text=omissions |
| IUCN and WPA status | Report, Species & nature tab | report=indira_point_table_3_16 · tab=Species & nature · text=IUCN category |
| Knowable at the time | Finding slips (Species & nature, Contradictions) | report=indira_point_table_3_16 · tab=Species & nature · css=.tf-knowable |
| Consultant accreditation (NABET) | Report, Public record tab | report=great_nicobar_2021_draft · tab=Public record · text=accreditation |
| Copied text | Report, Copied text tab | report=great_nicobar_2021_draft · tab=Copied text · text=Copied text |
| ToR promises, granted and proposed | Report, Promises & timeline tab | report=great_nicobar_2021_draft · tab=Promises & timeline · text=Granted ToR (MoEFCC letter |
| Survey timeline | Report, Promises & timeline tab | report=great_nicobar_2021_draft · tab=Promises & timeline · text=Proposed ToR ( |
| Official record check | Report, Public record tab | report=great_nicobar_2021_draft · tab=Public record · text=Does it match the official record? |
| Public record: what happened next | Report, Public record tab | report=great_nicobar_2021_draft · tab=Public record · text=What happened next |
| Paper trail: documents found | Report, Public record tab | report=great_nicobar_2021_draft · tab=Public record · text=Documents found |
| Authority contacts (who to write to) | Report, Public record tab | report=great_nicobar_2021_draft · tab=Public record · text=Who to write to |
| Evidence from the web | Report, Public record tab (expander) | report=great_nicobar_2021_draft · tab=Public record · text=Evidence from the web |
| Reviewer's memo | Report, Ask & investigate tab | report=great_nicobar_2021_draft · tab=Ask & investigate · text=Reviewer's memo |
| Ask the report | Report, Ask & investigate tab | report=great_nicobar_2021_draft · tab=Ask & investigate · text=Ask the report |
| Objection letter (English, Hindi; Tamil or Kannada for those states) | Report, Take action tab | report=great_nicobar_2021_draft · tab=Take action · text=Letter language |
| Tamil letter | Report, Take action tab (Tamil Nadu reports) | report=cuddalore_port_2026_draft · tab=Take action · text=Tamil |
| RTI and public hearing pack | Report, Take action tab | report=great_nicobar_2021_draft · tab=Take action · text=RTI + public hearing pack (.zip) |
| Review queue | Report, Quality tab | report=great_nicobar_2021_draft · tab=Quality · text=Every new RED/ORANGE flag |
| Precision | Report, Quality tab | report=great_nicobar_2021_draft · tab=Quality · text=Precision |
| Evaluation | Report, Quality tab | report=great_nicobar_2021_draft · tab=Quality · text=Evaluation |
| Cost card | Report, Cost & models tab | report=great_nicobar_2021_draft · tab=Cost & models · text=Cost per full audit, by triage mode |
| Context efficiency | Report, Cost & models tab | report=great_nicobar_2021_draft · tab=Cost & models · text=Context efficiency |
| Super-VL scanned-page inspector | Report, Cost & models tab | report=great_nicobar_2021_draft · tab=Cost & models · text=How TigerFish reads scanned pages |
| Report library with live totals | Home (below the opening row) and Library | css=.tf-lib-total |
| Library search | Library side panel | text=Search by project name |
| Library filters: State, Sector, Year, Audit type | Library side panel | text=Audit type |
| Filter: Has RED flags | Library side panel | text=Has RED flags |
| Filter: Has human-verified findings | Library side panel | text=Has human-verified findings |
| Upload with three levels | Top menu, Upload | menu=Upload · text=Deep audit (chosen pages, live) |
| Page picks for the deep audit | Upload page (after a PDF is read) | menu=Upload · text=pages you choose |
| How it works (diagram, levels, models) | Top menu, How it works | menu=How it works · text=Three levels |
| Limitations | Top menu, Limitations | menu=Limitations · text=Failure cases from our own runs |
