"""Weather and research claims exceed the chooser budget through repeated metadata.

The exact synthetic Tarquinia worker capture was 12,381 characters with spaces
(11,810 compact); the existing step/capability sharing still left 9,800. The
source payload is embedded so CI needs no temporary file or provider access.
Real chooser/manager/Gemini SDK requests terminate in the existing fake HTTP
transport. These checks concern lossless transport, not model judgement quality.
The second exact capture adds research with distinct provenance: a single table
still leaves 9,049 characters; contiguous evidence tables preserve every row.
"""
from copy import deepcopy
import hashlib
import json
from unittest.mock import AsyncMock

from mongomock_motor import AsyncMongoMockClient
import pytest

from agent import reasoning
from scripts import autonomy_completion_eval_v162 as gate
from test_agent_preparation_dependency_v162 import fake_gemini
from test_pending_outcome_contract_v162 import synthetic_transport_only  # noqa: F401


CAPTURE_SHA256 = "e8ed0e11a2be873d1d3efa40d7534f4790b3a4be3bd77b601fb73ae237b31141"
CAPTURED_CONTEXT = json.loads(r"""
{
  "goal": {
    "objective": "Sapere quando ritirare i panni presumibilmente asciutti o prima in caso di rischio.",
    "source_kind": "situation_initial_review",
    "source_refs": [
      "situation:sit_6ac6e599828c4a62",
      "place:eval-tarquinia-public-point"
    ],
    "user_clarifications_not_authority": [],
    "current_source_situation": {
      "situation_id": "sit_6ac6e599828c4a62",
      "situation_revision": "1",
      "attention_epoch": "1",
      "attention_started_at": "2026-10-12T10:01:57.234377+00:00",
      "attention_expected": "true"
    },
    "desired_outcome": "Sapere quando ritirare i panni presumibilmente asciutti o prima in caso di rischio.",
    "why_now": "La situazione ha un'intenzione di attenzione ancora aperta.",
    "success_criteria": [
      "Usare le fonti pertinenti disponibili, senza inventare condizioni o tempi.",
      "Scegliere un controllo successivo solo se ha un'utilità concreta.",
      "Un risultato fisico non si presume dal tempo trascorso.",
      "Consegnare una stima utile del momento d'azione o l'azione necessaria adesso; leggere una fonte da sola non completa il lavoro."
    ],
    "stop_conditions": [
      "La situazione viene risolta, annullata o l'attenzione revocata.",
      "L'AI conclude il lavoro con un risultato utile verificabile."
    ],
    "status": "active",
    "situation_outcome": null,
    "source_context": [
      {
        "ref": "situation:sit_6ac6e599828c4a62",
        "source": "situation",
        "id": "sit_6ac6e599828c4a62",
        "status": "active",
        "summary": "Panni appena stesi all'aperto a Tarquinia.",
        "semantic_kind": null,
        "temporal_scope": null,
        "attention_intent": "Riesaminare le fonti e indicare il momento utile al ritiro.",
        "desired_outcome": "Sapere quando ritirare i panni presumibilmente asciutti o prima in caso di rischio.",
        "started_at": "2026-10-12T10:01:56.336335+00:00",
        "created_at": "2026-10-12T10:01:57.233272+00:00",
        "icon_key": "other",
        "tracking_summary": null,
        "location_label": "Tarquinia",
        "current_state_summary": null,
        "expected_outcome_summary": null,
        "next_check_summary": null,
        "participants": [],
        "constraints": [],
        "facts": [
          "I panni sono stati appena stesi all'aperto."
        ],
        "assumptions": [],
        "linked_plan_id": null,
        "linked_object_refs": [
          "place:eval-tarquinia-public-point"
        ],
        "revision": 1,
        "updated_at": "2026-10-12T10:01:57.233274+00:00"
      }
    ],
    "source_context_unavailable": false
  },
  "plan": {
    "plan_summary": "Fonti attuali, base empirica e riesame.",
    "steps": [
      {
        "id": "stp_afc53248a91e423a",
        "ordinal": 0,
        "intent": "Leggere il meteo del luogo",
        "type": "inspect",
        "status": "succeeded",
        "capability_needed": "weather.read",
        "input_refs": [
          "place:eval-tarquinia-public-point"
        ],
        "document_offset": null,
        "document_version": null,
        "memory_offset": null,
        "memory_version": null,
        "wait_until": null,
        "wait_minutes": null,
        "wait_hours": null,
        "execution_parameters": null,
        "expected_result": null,
        "external_effect": false,
        "what_kind_of_change": "create",
        "effect_target": null,
        "reaches_somebody_else": false,
        "reversibility": "easily",
        "note": "Ho letto la risposta meteo per Tarquinia: 6 elementi; osservazione recente del provider."
      },
      {
        "id": "stp_1f49af3718344a79",
        "ordinal": 1,
        "intent": "Cercare una base empirica pertinente",
        "type": "research",
        "status": "pending",
        "capability_needed": "web.research",
        "input_refs": [],
        "document_offset": null,
        "document_version": null,
        "memory_offset": null,
        "memory_version": null,
        "wait_until": null,
        "wait_minutes": null,
        "wait_hours": null,
        "execution_parameters": null,
        "expected_result": "Quali misure pubbliche sostengono una stima prudente con queste condizioni?",
        "external_effect": false,
        "what_kind_of_change": "create",
        "effect_target": null,
        "reaches_somebody_else": false,
        "reversibility": "easily",
        "note": null
      },
      {
        "id": "stp_ff888d57fd914586",
        "ordinal": 2,
        "intent": "Rileggere le condizioni al controllo successivo",
        "type": "verify",
        "status": "pending",
        "capability_needed": "weather.read",
        "input_refs": [],
        "document_offset": null,
        "document_version": null,
        "memory_offset": null,
        "memory_version": null,
        "wait_until": null,
        "wait_minutes": null,
        "wait_hours": null,
        "execution_parameters": null,
        "expected_result": null,
        "external_effect": false,
        "what_kind_of_change": "create",
        "effect_target": null,
        "reaches_somebody_else": false,
        "reversibility": "easily",
        "note": null
      }
    ],
    "assumptions": [],
    "known_constraints": [],
    "expected_outcome": "",
    "revisions": 0
  },
  "local_clock": {
    "local_datetime": "2026-10-12T12:02:27+02:00",
    "local_time": "12:02",
    "local_date": "2026-10-12",
    "timezone": "Europe/Rome",
    "authority": "user_confirmed",
    "today": "2026-10-12",
    "today_weekday": "Monday"
  },
  "still_to_do": [
    {
      "id": "stp_1f49af3718344a79",
      "ordinal": 1,
      "intent": "Cercare una base empirica pertinente",
      "type": "research",
      "status": "pending",
      "capability_needed": "web.research",
      "input_refs": [],
      "document_offset": null,
      "document_version": null,
      "memory_offset": null,
      "memory_version": null,
      "wait_until": null,
      "wait_minutes": null,
      "wait_hours": null,
      "execution_parameters": null,
      "expected_result": "Quali misure pubbliche sostengono una stima prudente con queste condizioni?",
      "external_effect": false,
      "what_kind_of_change": "create",
      "effect_target": null,
      "reaches_somebody_else": false,
      "reversibility": "easily",
      "note": null
    },
    {
      "id": "stp_ff888d57fd914586",
      "ordinal": 2,
      "intent": "Rileggere le condizioni al controllo successivo",
      "type": "verify",
      "status": "pending",
      "capability_needed": "weather.read",
      "input_refs": [],
      "document_offset": null,
      "document_version": null,
      "memory_offset": null,
      "memory_version": null,
      "wait_until": null,
      "wait_minutes": null,
      "wait_hours": null,
      "execution_parameters": null,
      "expected_result": null,
      "external_effect": false,
      "what_kind_of_change": "create",
      "effect_target": null,
      "reaches_somebody_else": false,
      "reversibility": "easily",
      "note": null
    }
  ],
  "what_has_been_found": [
    {
      "evidence_id": "evd_956948d78c8f408a",
      "what_was_found": "Fonte meteo: open_meteo; luogo richiesto: Tarquinia; osservazione: 2026-10-12T12:02:00+02:00; fuso provider: Europe/Rome; risposta letta da ORA: 2026-10-12T10:02:27.293809+00:00. L'ora di lettura non aggiorna l'osservazione e la previsione non misura l'esito fisico.",
      "bears_on": "provenienza, luogo e validità temporale del meteo",
      "where_this_came_from": "external_research",
      "capability": "weather.read",
      "source_refs": [
        "place:eval-tarquinia-public-point",
        "situation:sit_6ac6e599828c4a62:revision:1",
        "place_snapshot:eval-tarquinia-public-point:2026-10-12T10:01:56.339041+00:00"
      ],
      "observed_at": "2026-10-12T12:02:00+02:00",
      "really_happened": true,
      "how_old": "fresh",
      "research_sufficient": null,
      "research_valid_until": null,
      "weather_valid_until": "2026-10-12T11:32:00+00:00",
      "note": "Osservazione del provider; fuso Europe/Rome. Il recupero della risposta non prova l'attualità dei dati né l'esito fisico."
    },
    {
      "evidence_id": "evd_87493c56c2484bf7",
      "what_was_found": "Condizioni riportate a Tarquinia all'osservazione 2026-10-12T12:02:00+02:00: Poco nuvoloso, 21 °C, umidità 55%, vento 12 km/h, precipitazioni 0 mm",
      "bears_on": "condizioni meteo all'orario dell'osservazione",
      "where_this_came_from": "external_research",
      "capability": "weather.read",
      "source_refs": [
        "place:eval-tarquinia-public-point",
        "situation:sit_6ac6e599828c4a62:revision:1",
        "place_snapshot:eval-tarquinia-public-point:2026-10-12T10:01:56.339041+00:00"
      ],
      "observed_at": "2026-10-12T12:02:00+02:00",
      "really_happened": true,
      "how_old": "fresh",
      "research_sufficient": null,
      "research_valid_until": null,
      "weather_valid_until": "2026-10-12T11:32:00+00:00",
      "note": "Osservazione del provider; fuso Europe/Rome. Il recupero della risposta non prova l'attualità dei dati né l'esito fisico."
    },
    {
      "evidence_id": "evd_5d2e7f0a36a64f89",
      "what_was_found": "Nel profilo orario del provider la probabilità massima di pioggia indicata dal provider è 10%.",
      "bears_on": "probabilità di pioggia nel profilo orario, distinta dall'intensità",
      "where_this_came_from": "external_research",
      "capability": "weather.read",
      "source_refs": [
        "place:eval-tarquinia-public-point",
        "situation:sit_6ac6e599828c4a62:revision:1",
        "place_snapshot:eval-tarquinia-public-point:2026-10-12T10:01:56.339041+00:00"
      ],
      "observed_at": "2026-10-12T12:02:00+02:00",
      "really_happened": true,
      "how_old": "fresh",
      "research_sufficient": null,
      "research_valid_until": null,
      "weather_valid_until": "2026-10-12T11:32:00+00:00",
      "note": "Osservazione del provider; fuso Europe/Rome. Il recupero della risposta non prova l'attualità dei dati né l'esito fisico."
    },
    {
      "evidence_id": "evd_b88041099fcd454f",
      "what_was_found": "Nel profilo orario del provider la temperatura prevista va circa da 21 a 21 °C.",
      "bears_on": "temperatura nel profilo orario del provider",
      "where_this_came_from": "external_research",
      "capability": "weather.read",
      "source_refs": [
        "place:eval-tarquinia-public-point",
        "situation:sit_6ac6e599828c4a62:revision:1",
        "place_snapshot:eval-tarquinia-public-point:2026-10-12T10:01:56.339041+00:00"
      ],
      "observed_at": "2026-10-12T12:02:00+02:00",
      "really_happened": true,
      "how_old": "fresh",
      "research_sufficient": null,
      "research_valid_until": null,
      "weather_valid_until": "2026-10-12T11:32:00+00:00",
      "note": "Osservazione del provider; fuso Europe/Rome. Il recupero della risposta non prova l'attualità dei dati né l'esito fisico."
    },
    {
      "evidence_id": "evd_1020b343598040bf",
      "what_was_found": "Profilo previsto: 2026-10-12T13:00:00+02:00, 21°C, umidità 55%, vento 12 km/h, pioggia 10% | 2026-10-12T14:00:00+02:00, 21°C, umidità 55%, vento 12 km/h, pioggia 10% | 2026-10-12T15:00:00+02:00, 21°C, umidità 55%, vento 12 km/h, pioggia 10%",
      "bears_on": "andamento orario delle condizioni ambientali",
      "where_this_came_from": "external_research",
      "capability": "weather.read",
      "source_refs": [
        "place:eval-tarquinia-public-point",
        "situation:sit_6ac6e599828c4a62:revision:1",
        "place_snapshot:eval-tarquinia-public-point:2026-10-12T10:01:56.339041+00:00"
      ],
      "observed_at": "2026-10-12T12:02:00+02:00",
      "really_happened": true,
      "how_old": "fresh",
      "research_sufficient": null,
      "research_valid_until": null,
      "weather_valid_until": "2026-10-12T11:32:00+00:00",
      "note": "Osservazione del provider; fuso Europe/Rome. Il recupero della risposta non prova l'attualità dei dati né l'esito fisico."
    },
    {
      "evidence_id": "evd_2ae763ece77f4b47",
      "what_was_found": "Profilo previsto: 2026-10-12T16:00:00+02:00, 21°C, umidità 55%, vento 12 km/h, pioggia 10% | 2026-10-12T17:00:00+02:00, 21°C, umidità 55%, vento 12 km/h, pioggia 10% | 2026-10-12T18:00:00+02:00, 21°C, umidità 55%, vento 12 km/h, pioggia 10%",
      "bears_on": "andamento orario delle condizioni ambientali",
      "where_this_came_from": "external_research",
      "capability": "weather.read",
      "source_refs": [
        "place:eval-tarquinia-public-point",
        "situation:sit_6ac6e599828c4a62:revision:1",
        "place_snapshot:eval-tarquinia-public-point:2026-10-12T10:01:56.339041+00:00"
      ],
      "observed_at": "2026-10-12T12:02:00+02:00",
      "really_happened": true,
      "how_old": "fresh",
      "research_sufficient": null,
      "research_valid_until": null,
      "weather_valid_until": "2026-10-12T11:32:00+00:00",
      "note": "Osservazione del provider; fuso Europe/Rome. Il recupero della risposta non prova l'attualità dei dati né l'esito fisico."
    },
    {
      "evidence_id": "evd_3888ef57aaca46f1",
      "what_was_found": "Oggi: Poco nuvoloso, 15–23 °C, pioggia max 10%",
      "bears_on": "previsione meteo giornaliera",
      "where_this_came_from": "external_research",
      "capability": "weather.read",
      "source_refs": [
        "place:eval-tarquinia-public-point",
        "situation:sit_6ac6e599828c4a62:revision:1",
        "place_snapshot:eval-tarquinia-public-point:2026-10-12T10:01:56.339041+00:00"
      ],
      "observed_at": "2026-10-12T12:02:00+02:00",
      "really_happened": true,
      "how_old": "fresh",
      "research_sufficient": null,
      "research_valid_until": null,
      "weather_valid_until": "2026-10-12T11:32:00+00:00",
      "note": "Osservazione del provider; fuso Europe/Rome. Il recupero della risposta non prova l'attualità dei dati né l'esito fisico."
    }
  ],
  "what_ora_can_do": [
    {
      "capability": "information.read",
      "status": "available_real",
      "can_be_used_now": true,
      "really_does_something": true,
      "changes_something_in_the_world": false,
      "why_not": null
    },
    {
      "capability": "weather.read",
      "status": "available_real",
      "can_be_used_now": true,
      "really_does_something": true,
      "changes_something_in_the_world": false,
      "why_not": null
    },
    {
      "capability": "web.research",
      "status": "available_real",
      "can_be_used_now": true,
      "really_does_something": true,
      "changes_something_in_the_world": false,
      "why_not": null
    }
  ]
}
""")


SECOND_CAPTURE_SHA256 = "bb5a7cff58150d1bd2b8c34ba2265088fc99fa0b9e796fc3daf922f6b9aa1873"
SECOND_CAPTURED_CONTEXT = json.loads(r"""
{
  "goal": {
    "objective": "Sapere quando ritirare i panni presumibilmente asciutti o prima in caso di rischio.",
    "source_kind": "situation_initial_review",
    "source_refs": [
      "situation:sit_1fed386127d549e6",
      "place:eval-tarquinia-public-point"
    ],
    "user_clarifications_not_authority": [],
    "current_source_situation": {
      "situation_id": "sit_1fed386127d549e6",
      "situation_revision": "1",
      "attention_epoch": "1",
      "attention_started_at": "2026-10-12T10:12:01.355405+00:00",
      "attention_expected": "true"
    },
    "desired_outcome": "Sapere quando ritirare i panni presumibilmente asciutti o prima in caso di rischio.",
    "why_now": "La situazione ha un'intenzione di attenzione ancora aperta.",
    "success_criteria": [
      "Usare le fonti pertinenti disponibili, senza inventare condizioni o tempi.",
      "Scegliere un controllo successivo solo se ha un'utilità concreta.",
      "Un risultato fisico non si presume dal tempo trascorso.",
      "Consegnare una stima utile del momento d'azione o l'azione necessaria adesso; leggere una fonte da sola non completa il lavoro."
    ],
    "stop_conditions": [
      "La situazione viene risolta, annullata o l'attenzione revocata.",
      "L'AI conclude il lavoro con un risultato utile verificabile."
    ],
    "status": "active",
    "situation_outcome": null,
    "source_context": [
      {
        "ref": "situation:sit_1fed386127d549e6",
        "source": "situation",
        "id": "sit_1fed386127d549e6",
        "status": "active",
        "summary": "Panni appena stesi all'aperto a Tarquinia.",
        "semantic_kind": null,
        "temporal_scope": null,
        "attention_intent": "Riesaminare le fonti e indicare il momento utile al ritiro.",
        "desired_outcome": "Sapere quando ritirare i panni presumibilmente asciutti o prima in caso di rischio.",
        "started_at": "2026-10-12T10:12:00.343384+00:00",
        "created_at": "2026-10-12T10:12:01.353326+00:00",
        "icon_key": "other",
        "tracking_summary": null,
        "location_label": "Tarquinia",
        "current_state_summary": null,
        "expected_outcome_summary": null,
        "next_check_summary": null,
        "participants": [],
        "constraints": [],
        "facts": [
          "I panni sono stati appena stesi all'aperto."
        ],
        "assumptions": [],
        "linked_plan_id": null,
        "linked_object_refs": [
          "place:eval-tarquinia-public-point"
        ],
        "revision": 1,
        "updated_at": "2026-10-12T10:12:01.353329+00:00"
      }
    ],
    "source_context_unavailable": false
  },
  "plan": {
    "plan_summary": "Fonti attuali, base empirica e riesame.",
    "steps": [
      {
        "id": "stp_1c5ac856bac04a2c",
        "ordinal": 0,
        "intent": "Leggere il meteo del luogo",
        "type": "inspect",
        "status": "succeeded",
        "capability_needed": "weather.read",
        "input_refs": [
          "place:eval-tarquinia-public-point"
        ],
        "document_offset": null,
        "document_version": null,
        "memory_offset": null,
        "memory_version": null,
        "wait_until": null,
        "wait_minutes": null,
        "wait_hours": null,
        "execution_parameters": null,
        "expected_result": null,
        "external_effect": false,
        "what_kind_of_change": "create",
        "effect_target": null,
        "reaches_somebody_else": false,
        "reversibility": "easily",
        "note": "Ho letto la risposta meteo per Tarquinia: 6 elementi; osservazione recente del provider."
      },
      {
        "id": "stp_40fe8c62205c4857",
        "ordinal": 1,
        "intent": "Cercare una base empirica pertinente",
        "type": "research",
        "status": "succeeded",
        "capability_needed": "web.research",
        "input_refs": [],
        "document_offset": null,
        "document_version": null,
        "memory_offset": null,
        "memory_version": null,
        "wait_until": null,
        "wait_minutes": null,
        "wait_hours": null,
        "execution_parameters": null,
        "expected_result": "Quali misure pubbliche sostengono una stima prudente con queste condizioni?",
        "external_effect": false,
        "what_kind_of_change": "create",
        "effect_target": null,
        "reaches_somebody_else": false,
        "reversibility": "easily",
        "note": "Ho cercato: Quali misure pubbliche sostengono una stima prudente con queste condizioni?. Fixture non reale: con condizioni ambientali analoghe il campione di tessuto richiedeva una finestra di 3–5 ore"
      },
      {
        "id": "stp_e242ba927c1c48d1",
        "ordinal": 2,
        "intent": "Rileggere le condizioni al controllo successivo",
        "type": "verify",
        "status": "pending",
        "capability_needed": "weather.read",
        "input_refs": [],
        "document_offset": null,
        "document_version": null,
        "memory_offset": null,
        "memory_version": null,
        "wait_until": null,
        "wait_minutes": null,
        "wait_hours": null,
        "execution_parameters": null,
        "expected_result": null,
        "external_effect": false,
        "what_kind_of_change": "create",
        "effect_target": null,
        "reaches_somebody_else": false,
        "reversibility": "easily",
        "note": null
      }
    ],
    "assumptions": [],
    "known_constraints": [],
    "expected_outcome": "",
    "revisions": 0
  },
  "local_clock": {
    "local_datetime": "2026-10-12T12:12:31+02:00",
    "local_time": "12:12",
    "local_date": "2026-10-12",
    "timezone": "Europe/Rome",
    "authority": "user_confirmed",
    "today": "2026-10-12",
    "today_weekday": "Monday"
  },
  "still_to_do": [
    {
      "id": "stp_e242ba927c1c48d1",
      "ordinal": 2,
      "intent": "Rileggere le condizioni al controllo successivo",
      "type": "verify",
      "status": "pending",
      "capability_needed": "weather.read",
      "input_refs": [],
      "document_offset": null,
      "document_version": null,
      "memory_offset": null,
      "memory_version": null,
      "wait_until": null,
      "wait_minutes": null,
      "wait_hours": null,
      "execution_parameters": null,
      "expected_result": null,
      "external_effect": false,
      "what_kind_of_change": "create",
      "effect_target": null,
      "reaches_somebody_else": false,
      "reversibility": "easily",
      "note": null
    }
  ],
  "what_has_been_found": [
    {
      "evidence_id": "evd_54819be464484684",
      "what_was_found": "Fonte meteo: open_meteo; luogo richiesto: Tarquinia; osservazione: 2026-10-12T12:12:00+02:00; fuso provider: Europe/Rome; risposta letta da ORA: 2026-10-12T10:12:31.424966+00:00. L'ora di lettura non aggiorna l'osservazione e la previsione non misura l'esito fisico.",
      "bears_on": "provenienza, luogo e validità temporale del meteo",
      "where_this_came_from": "external_research",
      "capability": "weather.read",
      "source_refs": [
        "place:eval-tarquinia-public-point",
        "situation:sit_1fed386127d549e6:revision:1",
        "place_snapshot:eval-tarquinia-public-point:2026-10-12T10:12:00.346406+00:00"
      ],
      "observed_at": "2026-10-12T12:12:00+02:00",
      "really_happened": true,
      "how_old": "fresh",
      "research_sufficient": null,
      "research_valid_until": null,
      "weather_valid_until": "2026-10-12T11:42:00+00:00",
      "note": "Osservazione del provider; fuso Europe/Rome. Il recupero della risposta non prova l'attualità dei dati né l'esito fisico."
    },
    {
      "evidence_id": "evd_7347cbb83c9e47fa",
      "what_was_found": "Condizioni riportate a Tarquinia all'osservazione 2026-10-12T12:12:00+02:00: Poco nuvoloso, 21 °C, umidità 55%, vento 12 km/h, precipitazioni 0 mm",
      "bears_on": "condizioni meteo all'orario dell'osservazione",
      "where_this_came_from": "external_research",
      "capability": "weather.read",
      "source_refs": [
        "place:eval-tarquinia-public-point",
        "situation:sit_1fed386127d549e6:revision:1",
        "place_snapshot:eval-tarquinia-public-point:2026-10-12T10:12:00.346406+00:00"
      ],
      "observed_at": "2026-10-12T12:12:00+02:00",
      "really_happened": true,
      "how_old": "fresh",
      "research_sufficient": null,
      "research_valid_until": null,
      "weather_valid_until": "2026-10-12T11:42:00+00:00",
      "note": "Osservazione del provider; fuso Europe/Rome. Il recupero della risposta non prova l'attualità dei dati né l'esito fisico."
    },
    {
      "evidence_id": "evd_08320b0a996c4f87",
      "what_was_found": "Nel profilo orario del provider la probabilità massima di pioggia indicata dal provider è 10%.",
      "bears_on": "probabilità di pioggia nel profilo orario, distinta dall'intensità",
      "where_this_came_from": "external_research",
      "capability": "weather.read",
      "source_refs": [
        "place:eval-tarquinia-public-point",
        "situation:sit_1fed386127d549e6:revision:1",
        "place_snapshot:eval-tarquinia-public-point:2026-10-12T10:12:00.346406+00:00"
      ],
      "observed_at": "2026-10-12T12:12:00+02:00",
      "really_happened": true,
      "how_old": "fresh",
      "research_sufficient": null,
      "research_valid_until": null,
      "weather_valid_until": "2026-10-12T11:42:00+00:00",
      "note": "Osservazione del provider; fuso Europe/Rome. Il recupero della risposta non prova l'attualità dei dati né l'esito fisico."
    },
    {
      "evidence_id": "evd_72a7ab9d96e94610",
      "what_was_found": "Nel profilo orario del provider la temperatura prevista va circa da 21 a 21 °C.",
      "bears_on": "temperatura nel profilo orario del provider",
      "where_this_came_from": "external_research",
      "capability": "weather.read",
      "source_refs": [
        "place:eval-tarquinia-public-point",
        "situation:sit_1fed386127d549e6:revision:1",
        "place_snapshot:eval-tarquinia-public-point:2026-10-12T10:12:00.346406+00:00"
      ],
      "observed_at": "2026-10-12T12:12:00+02:00",
      "really_happened": true,
      "how_old": "fresh",
      "research_sufficient": null,
      "research_valid_until": null,
      "weather_valid_until": "2026-10-12T11:42:00+00:00",
      "note": "Osservazione del provider; fuso Europe/Rome. Il recupero della risposta non prova l'attualità dei dati né l'esito fisico."
    },
    {
      "evidence_id": "evd_911a993f94d94b12",
      "what_was_found": "Profilo previsto: 2026-10-12T13:00:00+02:00, 21°C, umidità 55%, vento 12 km/h, pioggia 10% | 2026-10-12T14:00:00+02:00, 21°C, umidità 55%, vento 12 km/h, pioggia 10% | 2026-10-12T15:00:00+02:00, 21°C, umidità 55%, vento 12 km/h, pioggia 10%",
      "bears_on": "andamento orario delle condizioni ambientali",
      "where_this_came_from": "external_research",
      "capability": "weather.read",
      "source_refs": [
        "place:eval-tarquinia-public-point",
        "situation:sit_1fed386127d549e6:revision:1",
        "place_snapshot:eval-tarquinia-public-point:2026-10-12T10:12:00.346406+00:00"
      ],
      "observed_at": "2026-10-12T12:12:00+02:00",
      "really_happened": true,
      "how_old": "fresh",
      "research_sufficient": null,
      "research_valid_until": null,
      "weather_valid_until": "2026-10-12T11:42:00+00:00",
      "note": "Osservazione del provider; fuso Europe/Rome. Il recupero della risposta non prova l'attualità dei dati né l'esito fisico."
    },
    {
      "evidence_id": "evd_7f48ee75d770499b",
      "what_was_found": "Profilo previsto: 2026-10-12T16:00:00+02:00, 21°C, umidità 55%, vento 12 km/h, pioggia 10% | 2026-10-12T17:00:00+02:00, 21°C, umidità 55%, vento 12 km/h, pioggia 10% | 2026-10-12T18:00:00+02:00, 21°C, umidità 55%, vento 12 km/h, pioggia 10%",
      "bears_on": "andamento orario delle condizioni ambientali",
      "where_this_came_from": "external_research",
      "capability": "weather.read",
      "source_refs": [
        "place:eval-tarquinia-public-point",
        "situation:sit_1fed386127d549e6:revision:1",
        "place_snapshot:eval-tarquinia-public-point:2026-10-12T10:12:00.346406+00:00"
      ],
      "observed_at": "2026-10-12T12:12:00+02:00",
      "really_happened": true,
      "how_old": "fresh",
      "research_sufficient": null,
      "research_valid_until": null,
      "weather_valid_until": "2026-10-12T11:42:00+00:00",
      "note": "Osservazione del provider; fuso Europe/Rome. Il recupero della risposta non prova l'attualità dei dati né l'esito fisico."
    },
    {
      "evidence_id": "evd_78ca02d6b59c4439",
      "what_was_found": "Oggi: Poco nuvoloso, 15–23 °C, pioggia max 10%",
      "bears_on": "previsione meteo giornaliera",
      "where_this_came_from": "external_research",
      "capability": "weather.read",
      "source_refs": [
        "place:eval-tarquinia-public-point",
        "situation:sit_1fed386127d549e6:revision:1",
        "place_snapshot:eval-tarquinia-public-point:2026-10-12T10:12:00.346406+00:00"
      ],
      "observed_at": "2026-10-12T12:12:00+02:00",
      "really_happened": true,
      "how_old": "fresh",
      "research_sufficient": null,
      "research_valid_until": null,
      "weather_valid_until": "2026-10-12T11:42:00+00:00",
      "note": "Osservazione del provider; fuso Europe/Rome. Il recupero della risposta non prova l'attualità dei dati né l'esito fisico."
    },
    {
      "evidence_id": "evd_bc03841c537f4ab5",
      "what_was_found": "Fixture non reale: con condizioni ambientali analoghe il campione di tessuto richiedeva una finestra di 3–5 ore. Tessuto, carico, esposizione e condizioni diverse limitano il trasferimento della misura; il bucato non è osservato.",
      "bears_on": "Quali misure pubbliche sostengono una stima prudente con queste condizioni?",
      "where_this_came_from": "external_research",
      "capability": "web.research",
      "source_refs": [
        "rr_1f54e1b923ca"
      ],
      "observed_at": "2026-10-12T10:12:31.437903+00:00",
      "really_happened": true,
      "how_old": "fresh",
      "research_sufficient": true,
      "research_valid_until": "2026-10-12T16:12:31.437865+00:00",
      "weather_valid_until": null,
      "note": "quanto bastano le fonti: sufficient; claim citate verificate: True"
    }
  ],
  "what_ora_can_do": [
    {
      "capability": "information.read",
      "status": "available_real",
      "can_be_used_now": true,
      "really_does_something": true,
      "changes_something_in_the_world": false,
      "why_not": null
    },
    {
      "capability": "weather.read",
      "status": "available_real",
      "can_be_used_now": true,
      "really_does_something": true,
      "changes_something_in_the_world": false,
      "why_not": null
    },
    {
      "capability": "web.research",
      "status": "available_real",
      "can_be_used_now": true,
      "really_does_something": true,
      "changes_something_in_the_world": false,
      "why_not": null
    }
  ]
}
""")


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def expand_records(value):
    if isinstance(value, list):
        return deepcopy(value)
    if "record_groups" in value:
        return [row for group in value["record_groups"] for row in expand_records(group)]
    result = []
    for index, values in enumerate(value["rows"]):
        row = deepcopy(value["common"])
        absent = value.get("missing", {}).get(str(index), [])
        row.update({key: deepcopy(item) for column, (key, item) in
                    enumerate(zip(value["columns"], values)) if column not in absent})
        result.append(row)
    return result


def assert_material_unchanged(sent, original):
    assert sent["goal"] == original["goal"]
    assert sent["local_clock"] == original["local_clock"]
    rows = expand_records(sent["what_has_been_found"])
    # JSON equality also distinguishes false from 0, and null from absent.
    assert json.dumps(rows, sort_keys=True, ensure_ascii=False) == json.dumps(
        original["what_has_been_found"], sort_keys=True, ensure_ascii=False)
    assert len(rows) == len(original["what_has_been_found"])
    assert expand_records(sent["what_ora_can_do"]) == original["what_ora_can_do"]
    plan_steps = expand_records(sent["plan"]["steps"])
    candidates = [next(step for step in plan_steps if step["id"] == candidate["id"])
                  if candidate.get("details_in") == "plan.steps" else candidate
                  for candidate in sent["still_to_do"]]
    steps = [next(candidate for candidate in candidates if candidate["id"] == step["id"])
             if step.get("details_in") == "still_to_do" else step for step in plan_steps]
    assert steps == original["plan"]["steps"]
    assert candidates == original["still_to_do"]
    assert {key: value for key, value in sent["plan"].items() if key != "steps"} == {
        key: value for key, value in original["plan"].items() if key != "steps"}


async def choose(payload):
    return await reasoning.choose_next_action(
        payload["goal"], plan=payload["plan"], candidates=payload["still_to_do"],
        evidence=payload["what_has_been_found"], capabilities=payload["what_ora_can_do"],
        clock_context=payload["local_clock"],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["execute", "wait"])
async def test_exact_tarquinia_capture_reaches_real_chooser_sdk_without_losing_material(monkeypatch, decision):
    payload = deepcopy(CAPTURED_CONTEXT)
    original = deepcopy(payload)
    serialized = json.dumps(payload, ensure_ascii=False)
    assert len(serialized) == 12381
    assert hashlib.sha256(serialized.encode()).hexdigest() == CAPTURE_SHA256
    assert len(compact(payload)) == 11810
    assert "prepared_result" not in payload
    answer = ({"decision": "execute", "step_id": payload["still_to_do"][0]["id"],
               "reasoning": "Synthetic selection of a supplied pending step."}
              if decision == "execute" else
              {"decision": "wait", "wait_minutes": 23,
               "reasoning": "Synthetic wait; no physical outcome is asserted."})

    def reply(system, sent):
        assert "what_has_been_found" in system and "evidence" in system.lower()
        assert "missing" in system and "Null remains null" in system
        assert isinstance(sent["what_has_been_found"], dict)
        assert len(compact(sent)) <= 9000
        assert_material_unchanged(sent, original)
        return answer

    transported = fake_gemini(monkeypatch, reply)
    db = AsyncMongoMockClient().action_evidence_table_v162
    with gate.isolated_engine(db, mode="live") as probe:
        result = await choose(payload)
        assert result == answer
        assert len(transported) == probe.model_attempts == probe.model_http_requests == 1
        assert not probe.network.blocked and not probe.blocked_effects and not probe.push_attempts
    assert payload == original


@pytest.mark.asyncio
async def test_exact_second_tarquinia_capture_reaches_chooser_after_weather_and_research(monkeypatch):
    payload = deepcopy(SECOND_CAPTURED_CONTEXT)
    original = deepcopy(payload)
    serialized = json.dumps(payload, ensure_ascii=False)
    assert len(serialized) == 12732 and len(compact(payload)) == 12179
    assert hashlib.sha256(serialized.encode()).hexdigest() == SECOND_CAPTURE_SHA256
    assert len(payload["what_has_been_found"]) == 8 and "prepared_result" not in payload
    assert [row["capability"] for row in payload["what_has_been_found"]] == ["weather.read"] * 7 + ["web.research"]
    answer = {"decision": "wait", "wait_minutes": 23,
              "reasoning": "Synthetic next review; no physical outcome is asserted."}

    def reply(system, sent):
        assert "record_groups" in system and "order" in system
        groups = sent["what_has_been_found"]["record_groups"]
        assert [len(expand_records(group)) for group in groups] == [7, 1]
        assert len(compact(sent)) <= 9000
        assert_material_unchanged(sent, original)
        return answer

    transported = fake_gemini(monkeypatch, reply)
    db = AsyncMongoMockClient().second_action_evidence_table_v162
    with gate.isolated_engine(db, mode="live") as probe:
        result = await choose(payload)
        assert result == answer
        assert len(transported) == probe.model_attempts == probe.model_http_requests == 1
        assert not probe.network.blocked and not probe.blocked_effects and not probe.push_attempts
    assert payload == original


def test_contiguous_groups_preserve_exact_metadata_types_order_and_missing_fields():
    absent = object()
    rows = []
    # Equal metadata reappears after other groups; it must not reorder records.
    for group, clock in enumerate((True, 1, None, absent, True)):
        for member in range(2):
            row = {"evidence_id": f"ev_{group}_{member}", "source_refs": ["source:synthetic"],
                   "capability": "information.read", "what_was_found": f"Distinct source row {group}/{member}",
                   "note": f"Group {group} read limit: " + chr(65 + group) * 240,
                   "read_cursor": None if member == 0 else {"offset": 0, "partial": False}}
            if clock is not absent:
                row["observed_at"] = clock
            if member == 1:
                row["nullable"] = None
            rows.append(row)
    original = deepcopy(rows)
    encoded = reasoning._evidence_record_groups(rows)
    groups = encoded["record_groups"]
    assert len(groups) == 5 and [len(expand_records(group)) for group in groups] == [2] * 5
    assert expand_records(groups[0])[0]["observed_at"] is True
    assert type(expand_records(groups[1])[0]["observed_at"]) is int
    assert expand_records(groups[2])[0]["observed_at"] is None
    assert "observed_at" not in expand_records(groups[3])[0]
    assert expand_records(groups[4])[0]["observed_at"] is True
    assert json.dumps(expand_records(encoded), sort_keys=True) == json.dumps(original, sort_keys=True)
    assert len(compact(encoded)) < len(compact(reasoning._record_table(original)))
    assert rows == original


def test_group_representation_is_not_used_when_it_would_be_larger():
    rows = [{"evidence_id": "a", "capability": "read.a"},
            {"evidence_id": "b", "capability": "read.b"}]
    original = deepcopy(rows)
    assert reasoning._evidence_record_groups(rows) == reasoning._record_table(rows) == original
    assert rows == original


def test_evidence_table_keeps_distinct_provenance_cursors_absent_null_and_false():
    payload = deepcopy(CAPTURED_CONTEXT)
    rows = payload["what_has_been_found"]
    rows[0].pop("note")
    rows[1]["note"] = None
    rows[2]["note"] = "Different read limit; not independently confirmed."
    rows[0]["research_sufficient"] = False
    rows[1]["research_sufficient"] = 0
    rows[2].pop("research_sufficient")
    rows[3]["observed_at"] = "2026-10-12T09:40:00+00:00"
    rows[3]["weather_valid_until"] = "2026-10-12T11:10:00+00:00"
    rows[4]["source_refs"] = ["situation:synthetic-other-revision:revision:2"]
    rows[5]["memory_reads"] = [{"ref": "mem_synthetic_partial", "version": "v2",
                               "offset": 0, "next_offset": 600, "partial": True}]
    rows[6]["memory_reads"] = None
    original = deepcopy(payload)
    encoded = reasoning._action_dump(payload)
    assert encoded is not None and len(encoded) <= 9000
    sent = json.loads(encoded)
    table = sent["what_has_been_found"]
    assert isinstance(table, dict) and table.get("missing")
    assert_material_unchanged(sent, original)
    assert payload == original


def test_context_already_within_budget_keeps_ordinary_evidence_list():
    payload = deepcopy(CAPTURED_CONTEXT)
    payload["what_has_been_found"] = payload["what_has_been_found"][:2]
    original = deepcopy(payload)
    assert len(compact(payload)) <= 9000
    encoded = reasoning._action_dump(payload)
    assert json.loads(encoded) == original
    assert isinstance(json.loads(encoded)["what_has_been_found"], list)
    assert payload == original


@pytest.mark.asyncio
async def test_genuinely_large_distinct_source_material_is_rejected_before_model(monkeypatch, caplog):
    payload = deepcopy(CAPTURED_CONTEXT)
    # Twelve distinct claims, each within the existing 600-character claim
    # bound; sharing metadata cannot make all this material fit with the goal.
    sample = payload["what_has_been_found"][0]
    payload["what_has_been_found"] = [
        dict(deepcopy(sample), evidence_id=f"evd_distinct_{index}",
             what_was_found=(f"Source {index}: " + chr(65 + index) * 600)[:600],
             source_refs=[f"source:synthetic:{index}"], bears_on=f"Distinct constraint {index}")
        for index in range(12)
    ]
    original = deepcopy(payload)
    ask = AsyncMock(side_effect=AssertionError("The oversized context must not call a model"))
    monkeypatch.setattr(reasoning, "_ask_model", ask)
    with caplog.at_level("INFO"):
        result = await choose(payload)
    assert result is None
    ask.assert_not_awaited()
    assert "material_context_exceeds_budget" in caplog.text
    assert payload == original
