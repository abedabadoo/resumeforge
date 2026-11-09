"""Synthetic, role-local evidence pairs. Test sources are disjoint from training sources."""
# (family, source evidence, supported paraphrase, unsupported close alternative)
TRAIN = [
 ('ownership', 'Supported the migration by testing three endpoints; the platform lead owned rollout.', 'Tested three endpoints in support of the migration.', 'Owned the rollout and tested three endpoints.'),
 ('outcome', 'Built a staging deployment script; no change to release frequency was measured.', 'Scripted deployments to staging.', 'Increased release frequency by scripting deployments to staging.'),
 ('scope', 'Reviewed accessibility on two internal dashboards.', 'Assessed two internal dashboards for accessibility issues.', 'Led an accessibility review across all company dashboards.'),
 ('metric', 'Cut mean build time from 24 minutes to 18 minutes.', 'Shortened builds from 24 to 18 minutes on average.', 'Reduced mean build time by 18 minutes.'),
 ('negation', 'Compared Airflow with Dagster; Dagster was not deployed.', 'Compared two orchestration tools, Airflow and Dagster.', 'Deployed Dagster after comparing it with Airflow.'),
 ('attribution', 'The infrastructure team operated Redis. I documented its incident runbook.', 'Documented the incident runbook for Redis.', 'Operated Redis and authored its incident runbook.'),
 ('frequency', 'Triaged billing alerts during the quarterly reconciliation.', 'Triaged billing alerts as part of quarterly reconciliation.', 'Triaged billing alerts daily throughout the year.'),
 ('training', 'Completed classroom exercises in Rust without using it at work.', 'Practiced Rust through classroom exercises.', 'Built Rust services for the employer.'),
 ('quantity', 'Reviewed 46 alerts and escalated 8 for investigation.', 'Escalated eight of the 46 alerts reviewed.', 'Resolved all 46 alerts and escalated eight investigations.'),
 ('causality', 'Created a runbook. Separately, the team reported fewer outages.', 'Created an operations runbook.', 'Reduced outages by creating an operations runbook.'),
 ('pilot', 'Evaluated the new search index on anonymized test data.', 'Tested the search index using anonymized data.', 'Launched the new index in production with live customer data.'),
 ('date', 'Served as interim supervisor for six weeks in 2023.', 'Supervised the team on an interim basis for six weeks in 2023.', 'Supervised the team for the entirety of 2023.')]
TEST = [
 ('role', 'At Harbor I installed Ubuntu; at Ridge I maintained Solaris.', 'Maintained Solaris at Ridge.', 'Maintained Solaris at Harbor.'),
 ('direction', 'Tickets rose from 30 to 40 after the team opened a new intake channel.', 'Recorded an increase in tickets following the new intake channel.', 'Decreased tickets from 40 to 30 by opening a new intake channel.'),
 ('measurement', 'Helped draft a patch checklist. The team did not track change failure rates.', 'Contributed to the patch checklist.', 'Improved the change failure rate through a patch checklist.'),
 ('recommendation', 'Proposed a move to Vault; security leadership postponed the project.', 'Recommended Vault as part of a postponed migration project.', 'Moved secrets to Vault for a project approved by security leadership.'),
 ('unit', 'Responded to 12 requests per quarter and spent 3 hours a week on documentation.', 'Handled 12 requests per quarter.', 'Handled 12 requests each week.'),
 ('leadership', 'Reported data quality concerns to the engineer who led the investigation.', 'Raised concerns about data quality with the investigating engineer.', 'Led the investigation into data quality concerns.'),
 ('tool_substitution', 'Automated report delivery with a shell script and a cron job.', 'Scheduled the reporting shell script with cron.', 'Scheduled the reporting shell script with Jenkins.'),
 ('stage', 'The build generated a container image. Another team deployed it.', 'Produced a container image during the build.', 'Deployed the container image to production.')]

def cases():
 for split,examples in [('train',TRAIN),('heldout',TEST)]:
  for family,evidence,yes,no in examples:
   for label,claim in ((1,yes),(0,no)):
    yield dict(id=f'{split}:{family}:{label}',split=split,family=family,evidence=evidence,claim=claim,label=label)

def prompt(c):
 return ('<|im_start|>system\nIs the entire resume claim established by the evidence? Answer Yes or No. Unsupported details require No.<|im_end|>\n'
         '<|im_start|>user\nEvidence: '+c['evidence']+'\nClaim: '+c['claim']+'<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n')
