"""Ten reviewed public Opportunity requests sharing one record-update strategy.

Values are authored from the public user messages and native Opportunity field
names. No hidden assertions or official-score behavior supply these contracts.
"""

from typing import Literal

from .record_update_evidence import RecordField, RecordUpdateContract, evaluate_record_update


def _contract(
    suffix,
    request,
    identity,
    field,
    value,
    comparison: Literal["string", "number", "integer", "calendar_date"] = "string",
    baseline=(),
):
    return RecordUpdateContract(
        revision="public_sf_opportunity_updates_v1",
        task_name="simple.sf_opp_" + suffix,
        user_request=request,
        service="salesforce",
        collection="opportunities",
        record_id=identity,
        desired_fields=(RecordField(field, value, comparison),),
        baseline_requirements=baseline,
    )


CONTRACTS = (
    _contract(
        "closed_won",
        "Great news - the NexGen Platform Deal (opportunity 006001) just closed! Please mark it as Closed Won in Salesforce.",
        "006001",
        "stage_name",
        "Closed Won",
    ),
    _contract(
        "stage_proposal",
        "Update opportunity 006002 (CloudBridge Migration) to stage 'Proposal/Price Quote' in Salesforce.",
        "006002",
        "stage_name",
        "Proposal/Price Quote",
    ),
    _contract(
        "amount_update",
        "Update the amount on opportunity 006003 (DataStream Analytics License) to $45,000 in Salesforce.",
        "006003",
        "amount",
        45000,
        "number",
    ),
    _contract(
        "close_date_update",
        "Push the close date on opportunity 006004 (Apex Security Suite) to 2026-03-31 in Salesforce.",
        "006004",
        "close_date",
        "2026-03-31",
        "calendar_date",
    ),
    _contract(
        "probability_update",
        "Update the probability on opportunity 006005 (Meridian ERP Rollout) to 75% in Salesforce.",
        "006005",
        "probability",
        75,
        "integer",
    ),
    _contract(
        "description_update",
        "Add the following description to opportunity 006006 (Vantage AI Integration): 'Client requested custom ML model integration with existing data pipeline. Timeline: Q2 2026.'",
        "006006",
        "description",
        "Client requested custom ML model integration with existing data pipeline. Timeline: Q2 2026.",
        baseline=(RecordField("description", ""),),
    ),
    _contract(
        "stage_value_prop",
        "Move opportunity 006007 (TerraForm Cloud Hosting) from 'Needs Analysis' to 'Value Proposition' in Salesforce.",
        "006007",
        "stage_name",
        "Value Proposition",
        baseline=(RecordField("stage_name", "Needs Analysis"),),
    ),
    _contract(
        "campaign_update",
        "Set the campaign_id on opportunity 006008 (Quantum Pay Gateway) to 'camp_2026_spring' in Salesforce.",
        "006008",
        "campaign_id",
        "camp_2026_spring",
    ),
    _contract(
        "next_step_update",
        "Update the next_step field on opportunity 006009 (Orion Fleet Management) to 'Schedule technical demo with engineering team' in Salesforce.",
        "006009",
        "next_step",
        "Schedule technical demo with engineering team",
    ),
    _contract(
        "type_update",
        "Update the type field on opportunity 006010 (Helios Solar Dashboard) to 'New Business' in Salesforce.",
        "006010",
        "type",
        "New Business",
    ),
)
SUPPORTED = frozenset(contract.task_name for contract in CONTRACTS)


def evaluate_simple_record_update(source: dict):
    task_name = source["task_evidence"]["task_name"]
    contract = next((contract for contract in CONTRACTS if contract.task_name == task_name), None)
    if contract is None:
        raise ValueError("simple_record_update_task_unimplemented")
    return evaluate_record_update(source, contract)
