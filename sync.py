import requests
import json
import os
import ast
import datetime as dt
from log_helper import app_log as log

# OPTIONS:
github_token = os.environ.get("GITHUB_TOKEN")
freshdesk_key = os.environ.get("FRESHDESK_KEY")
freshdesk_url = os.environ.get("FRESHDESK_URL")
org = os.environ.get("ORG")
language = os.environ.get("LANGUAGE")
project_number = os.environ.get("PROJECT")
status_field = os.environ.get("STATUS_FIELD")
priority_field = os.environ.get("PRIORITY_FIELD")
company_field = os.environ.get("COMPANY_FIELD")
iteration_field = os.environ.get("ITERATION_FIELD")
type_label_map = os.environ.get("TYPE_LABELS")
tag = os.environ.get("TAG")


# A simple function to use requests.post to make the API call. Note the json= section.
def github_run_query(query):
    request = requests.post(
        "https://api.github.com/graphql",
        json={"query": query},
        headers=github_graphql_header(),
    )
    if request.status_code == 200:
        return request.json()
    else:
        log.error(f"[red]Query fallita con codice {request.status_code}. Query: {query}")
        log.error(f"[red]Risposta: {request.text}")
        raise Exception(
            "Query failed to run by returning code of {}. {}".format(
                request.status_code, query
            )
        )


def github_graphql_header():
    headers = {}
    headers.update(github_auth())
    headers.update({"X-Github-Next-Global-ID": "1"})
    return headers


def github_auth():
    auth = {"Authorization": "Bearer " + github_token}
    return auth


def github_get_project_fields():
    log.info("[yellow]Getting Github Project Fields")
    query = f"""
        {{
        organization(login: "{org}"){{
            projectV2(number: {project_number}) {{
            fields(first: 20) {{
                nodes{{
                ...on ProjectV2SingleSelectField{{
                    id
                    name
                    options {{
                    id
                    name
                    description
                    }}
                }}
                ...on ProjectV2Field{{
                    id
                    name
                }}
                }}
            }}
            }}
        }}
        }}
    """
    response = github_run_query(query)
    fields = response["data"]["organization"]["projectV2"]["fields"]["nodes"]
    return fields


def github_get_project_statuses(fields: dict):
    for f in fields:
        if "name" in f:
            if f["name"] == status_field:
                options = []
                for o in f["options"]:
                    options.append(o["name"])
                return options


def github_get_project_priorities(fields: dict):
    for f in fields:
        if "name" in f:
            if f["name"] == priority_field:
                options = []
                for o in f["options"]:
                    option = {}
                    option.update({"name": o["name"]})
                    option.update({"id": o["id"]})
                    option.update({"field_id": f["id"]})
                    options.append(option)
                return options


def github_get_priority_option_id(priority: str, fields: dict):
    priority_options = github_get_project_priorities(fields=fields)
    option = next(opt for opt in priority_options if opt["name"] == priority)
    if option != {}:
        return option["id"], option["field_id"]


def github_get_company_field_id(fields: dict):
    for f in fields:
        if "name" in f:
            if f["name"] == company_field:
                return f["id"]


def github_get_members():
    url = f"https://api.github.com/orgs/{org}/members"
    auth = github_auth()
    response = requests.get(url=url, headers=auth)
    if response.status_code == 200:
        members = []
        for m in json.loads(response.content):
            members.append(m["login"])
        return members
    else:
        log.error(f"[red]Errore nel recupero dei membri Github: {response.reason}")
        log.error(f"[red]Contenuto risposta: {response.content.decode('utf-8')}")
        return [] # Restituisce una lista vuota in caso di errore


def github_get_repos():
    log.info("[yellow]Getting Github Repositories")
    url = f"https://api.github.com/orgs/{org}/repos"
    auth = github_auth()
    repos = []
    morepages = True
    while morepages:
        response = requests.get(url=url, headers=auth)
        if response.status_code == 200:
            content = json.loads(response.content)
            for r in content:
                if not r["archived"]:
                    if language != "":
                        if r["language"] == "AL":
                            repos.append(r["name"])
                    else:
                        repos.append(r["name"])
            try:
                url = response.links["next"]["url"]
            except:
                morepages = False
        else:
            log.error(f"[red]Errore nel recupero dei repository Github: {response.reason}")
            log.error(f"[red]Contenuto risposta: {response.content.decode('utf-8')}")
            morepages = False # Ferma il loop in caso di errore
    return repos


def github_get_project_cards(after_cursor=""):
    log.info("[yellow]Getting Github Project Items")
    query = f"""
        {{
            organization(login: "{org}") {{
                projectV2(number: {project_number}) {{
                id
                items(first: 100, after: "{after_cursor}") {{
                    edges {{
                    node {{
                        id
                        content {{
                        ... on Issue {{
                            id
                            number
                            title
                            repository {{
                            id
                            name
                            }}
                        }}
                        }}
                        fieldValues(first: 10, orderBy: {{field: POSITION, direction: ASC}}) {{
                        nodes {{
                            ... on ProjectV2ItemFieldTextValue {{
                            text
                            field {{
                                ... on ProjectV2Field {{
                                id
                                name
                                }}
                            }}
                            }}
                            ... on ProjectV2ItemFieldDateValue {{
                            date
                            field {{
                                ... on ProjectV2Field {{
                                id
                                name
                                }}
                            }}
                            }}
                            ... on ProjectV2ItemFieldSingleSelectValue {{
                            name
                            field {{
                                ... on ProjectV2SingleSelectField {{
                                id
                                name
                                }}
                            }}
                            }}
                            ... on ProjectV2ItemFieldIterationValue {{
                            title
                            startDate
                            duration
                            field {{
                                ... on ProjectV2IterationField {{
                                id
                                name
                                }}
                            }}
                            }}
                        }}
                        }}
                    }}
                    }}
                    pageInfo {{
                        endCursor
                        hasNextPage
                        hasPreviousPage
                    }}
                }}
                }}
            }}
        }}
    """
    response = github_run_query(query)
    cards = []
    for card in response["data"]["organization"]["projectV2"]["items"]["edges"]:
        if card["node"]["content"]:
            card_object = {}
            card_object["project_id"] = response["data"]["organization"]["projectV2"][
                "id"
            ]
            card_object["item_id"] = card["node"]["id"]
            card_object["title"] = card["node"]["content"]["title"]
            card_object["repository"] = card["node"]["content"]["repository"]["name"]
            card_object["issue_number"] = card["node"]["content"]["number"]
            card_object["issue_id"] = card["node"]["content"]["id"]
            for f in card["node"]["fieldValues"]["nodes"]:
                if f.get("field"):
                    if f["field"]["name"] == status_field:
                        card_object[status_field] = f["name"]
                    if f["field"]["name"] == company_field:
                        card_object[company_field] = f["text"]
                    if f["field"]["name"] == priority_field:
                        card_object[priority_field] = f["name"]
                    if f["field"]["name"] == iteration_field:
                        card_object[iteration_field] = f["startDate"]
                        iterationend = dt.datetime.strptime(
                            f["startDate"], "%Y-%m-%d"
                        ) + dt.timedelta(days=f["duration"])
                        card_object["iteration_end"] = iterationend.strftime("%Y-%m-%d")
            cards.append(card_object)
    if response["data"]["organization"]["projectV2"]["items"]["pageInfo"][
        "hasNextPage"
    ]:
        cards = cards + github_get_project_cards(
            after_cursor=response["data"]["organization"]["projectV2"]["items"][
                "pageInfo"
            ]["endCursor"]
        )
    return cards


def map_type_label(type: str):
    maplist = ast.literal_eval(type_label_map)
    for map in maplist:
        if type == map[0]:
            return map[1]
    return None


def github_build_issue(ticket: dict):
    issue = {}
    assignees = None
    title = (
        f"{ticket["custom_fields"]["cf_development_task_title"]} (FD#{ticket["id"]})"
    )
    body = f"{ticket["summary"]}\n\n<a href=https://{freshdesk_url}/a/tickets/{str(ticket['id'])}>Freshdeck Ticket #{str(ticket['id'])}</a>"
    label = [map_type_label(ticket["type"])]
    if ticket["custom_fields"]["cf_assigned_developer"] != None:
        assignees = [ticket["custom_fields"]["cf_assigned_developer"]]
    issue.update({"title": title})
    issue.update({"body": body})
    if assignees:
        issue.update({"assignees": assignees})
    if label != [None]:
        issue.update({"labels": label})
    return issue


def github_create_issue(ticket: dict, repo: str):
    issue = github_build_issue(ticket)
    if issue != {}:
        log.info("[yellow]Creating Github Issue " + str(issue))
        url = f"https://api.github.com/repos/{org}/{repo}/issues"
        auth = github_auth()
        response = requests.post(url=url, headers=auth, json=issue)
        if response.status_code == 201:
            gh_issue = json.loads(response.content)
            return gh_issue
        else:
            log.error(f"[red]Errore nella creazione dell'Issue Github: {response.reason}")
            log.error(f"[red]Contenuto risposta: {response.content.decode('utf-8')}")
            return {} # Restituisce un dizionario vuoto in caso di errore


def github_compare_issue_field(
    gh_issue: dict, field: str, value: str, updated_issue: dict
):
    if field in gh_issue:
        if field == "title":
            if value != gh_issue[field]:
                updated_issue.update({field: value})
        elif field == "body":
            if gh_issue[field] != None:
                existing_body = gh_issue[field]
            else:
                existing_body = ""
            if value not in existing_body:
                existing_body = existing_body + f"<br><br>{value}"
                updated_issue.update({field: existing_body})
        elif field == "labels":
            labelfound = False
            for l in gh_issue[field]:
                if l["name"] == value:
                    labelfound = True
            if not labelfound:
                updated_issue.update({field: [value]})


def github_update_issue(ticket: dict, gh_issue: dict, repo: str, card: dict):
    fd_assignee = ticket["custom_fields"]["cf_assigned_developer"]
    try:
        gh_assignee = gh_issue["assignee"]["login"]
    except:
        gh_assignee = None
    if gh_assignee != None:
        if fd_assignee != gh_assignee:
            card.update({"assignee": gh_assignee})
    title = (
        f"{ticket["custom_fields"]["cf_development_task_title"]} (FD#{ticket["id"]})"
    )
    body = f"<a href=https://{freshdesk_url}/a/tickets/{str(ticket['id'])}>Freshdeck Ticket #{str(ticket['id'])}</a>"
    label = map_type_label(ticket["type"])
    updated_issue = {}
    github_compare_issue_field(
        gh_issue=gh_issue, field="title", value=title, updated_issue=updated_issue
    )
    if label != None:
        github_compare_issue_field(
            gh_issue=gh_issue, field="labels", value=label, updated_issue=updated_issue
        )
    github_compare_issue_field(
        gh_issue=gh_issue, field="body", value=body, updated_issue=updated_issue
    )
    if updated_issue != {}:
        log.info(
            "[yellow]Updating Github Issue "
            + str(gh_issue["number"])
            + " "
            + str(updated_issue)
        )
        url = f"https://api.github.com/repos/{org}/{repo}/issues/{gh_issue['number']}"
        auth = github_auth()
        response = requests.patch(url=url, headers=auth, json=updated_issue)
        if response.status_code == 200:
            gh_issue = json.loads(response.content)
            return card
        else:
            log.error(f"[red]Errore nell'aggiornamento dell'Issue Github: {response.reason}")
            log.error(f"[red]Contenuto risposta: {response.content.decode('utf-8')}")
            return card # Restituisce la card originale in caso di errore
    else:
        return card


def github_get_issue(gh_issue_number: str, repo: str):
    log.info("[yellow]Getting Github Issue " + str(gh_issue_number))
    url = f"https://api.github.com/repos/{org}/{repo}/issues/{gh_issue_number}"
    auth = github_auth()
    response = requests.get(url=url, headers=auth)
    if response.status_code == 200:
        gh_issue = json.loads(response.content)
        return gh_issue
    else:
        log.error(f"[red]Errore nel recupero dell'Issue Github: {response.reason}")
        log.error(f"[red]Contenuto risposta: {response.content.decode('utf-8')}")
        return None # Restituisce None in caso di errore


def github_update_project_card(card: dict, company: str, priority: str, fields: dict):
    card_company = ""
    try:
        card_company = card[company_field]
    except:
        card_company = ""
    if company != card_company:
        log.info("[yellow]Updating Github Project Item " + str(card))
        card_id = card["item_id"]
        project_id = card["project_id"]
        field_id = github_get_company_field_id(fields=fields)
        # update company field
        query = """
            mutation {
                updateProjectV2ItemFieldValue(
                    input: {projectId: "%s", itemId: "%s", fieldId: "%s", value: {text: "%s" } }
                    ) {
                    clientMutationId
                    }
                }
        """ % (
            project_id,
            card_id,
            field_id,
            company,
        )
        response = github_run_query(query)
    card_priority = ""
    try:
        card_priority = card[priority_field]
    except:
        card_priority = ""
    if priority != card_priority:
        log.info("[yellow]Updating Github Project Item " + str(card))
        card_id = card["item_id"]
        project_id = card["project_id"]
        priority_option_id, field_id = github_get_priority_option_id(
            priority=priority, fields=fields
        )
        # update priority field
        query = """
            mutation {
                updateProjectV2ItemFieldValue(
                    input: {projectId: "%s", itemId: "%s", fieldId: "%s", value: {singleSelectOptionId: "%s" } }
                    ) {
                    clientMutationId
                    }
            }
        """ % (
            project_id,
            card_id,
            field_id,
            priority_option_id,
        )
        response = github_run_query(query)


def freshdesk_headers():
    header = {"Content-Type": "application/json"}
    auth = (freshdesk_key, "X")
    return header, auth


def freshdesk_get_fields():
    log.info("[yellow]Getting Freshdesk Fields")
    url = f"https://{freshdesk_url}/api/v2/admin/ticket_fields"
    headers, auth = freshdesk_headers()
    response = requests.get(url=url, headers=headers, auth=auth)
    if response.status_code == 200:
        return json.loads(response.content)
    else:
        log.error(f"[red]Errore nel recupero dei campi Freshdesk: {response.reason}")
        log.error(f"[red]Contenuto risposta: {response.content.decode('utf-8')}")
        return [] # Restituisce una lista vuota in caso di errore


def freshdesk_get_field_id(field_name: str, fields: list):
    for f in fields:
        if f["name"] == field_name:
            return f["id"]
    return None # Aggiunto per gestire il caso in cui il campo non venga trovato


def freshdesk_get_company_name(ticket: dict):
    if ticket["company_id"]:
        url = f"https://{freshdesk_url}//api/v2/companies/{ticket["company_id"]}"
        headers, auth = freshdesk_headers()
        response = requests.get(url=url, headers=headers, auth=auth)
        if response.status_code == 200:
            return json.loads(response.content)["name"]
        else:
            log.error(f"[red]Errore nel recupero del nome azienda Freshdesk: {response.reason}")
            log.error(f"[red]Contenuto risposta: {response.content.decode('utf-8')}")
            return None # Restituisce None in caso di errore


def freshdesk_create_field(field: dict):
    log.info("[yellow]Creating Freshdesk Field " + str(field))
    url = f"https://{freshdesk_url}/api/v2/admin/ticket_fields"
    headers, auth = freshdesk_headers()
    response = requests.post(url=url, headers=headers, json=field, auth=auth)
    if response.status_code == 201:
        log.info(f"[green]Campo Freshdesk '{field.get('label', 'Sconosciuto')}' creato con successo.")
        return json.loads(response.content)
    else:
        log.error(f"[red]Errore nella creazione del campo Freshdesk '{field.get('label', 'Sconosciuto')}': {response.reason}")
        log.error(f"[red]Codice di stato: {response.status_code}")
        log.error(f"[red]Contenuto risposta: {response.text}")
        return None # Importante: restituisce None in caso di errore


def freshdesk_view_field(field_name: str, fields: list):
    field_id = freshdesk_get_field_id(field_name, fields)
    if field_id is None:
        log.warning(f"[yellow]Campo Freshdesk '{field_name}' non trovato tra i campi esistenti.")
        return None # Restituisce None se l'ID non viene trovato
    
    url = f"https://{freshdesk_url}/api/v2/admin/ticket_fields/{field_id}"
    headers, auth = freshdesk_headers()
    response = requests.get(url=url, headers=headers, auth=auth)
    if response.status_code == 200:
        return json.loads(response.content)
    else:
        log.error(f"[red]Errore nella visualizzazione del campo Freshdesk '{field_name}': {response.reason}")
        log.error(f"[red]Codice di stato: {response.status_code}")
        log.error(f"[red]Contenuto risposta: {response.text}")
        return None # Importante: restituisce None in caso di errore


def freshdesk_get_field_choices(response: dict):
    # Aggiunto controllo per assicurarsi che 'response' non sia None
    if response and "choices" in response:
        return response["choices"]
    return [] # Restituisce una lista vuota se le scelte non sono disponibili


def freshdesk_field_choice_exists(field_choices: dict, choice: str):
    # Assicurati che field_choices sia una lista prima di iterare
    if not isinstance(field_choices, list):
        return False
    for c in field_choices:
        if choice in c.get("value", ""): # Usare .get per sicurezza
            return True
    return False


def freshdesk_add_field_choice(field: dict, field_choices: list, new_value: str):
    # Questa logica sembra creare una nuova lista con solo la nuova scelta,
    # invece di aggiungere alla lista esistente. Potrebbe essere un bug logico.
    # Se l'intento è aggiungere, la logica dovrebbe essere:
    # field_choices.append(new_choice)
    # updated_field.update({"choices": field_choices})
    # Per ora, mantengo la logica originale ma segnalo la potenziale anomalia.

    if not field_choices:
        field_choices = []
    max_position = 0
    for c in field_choices:
        if c.get("position", 0) > max_position: # Usare .get per sicurezza
            max_position = c["position"]
    new_choice = {}
    new_choice.update({"label": new_value})
    new_choice.update({"value": new_value})
    new_choice.update({"position": max_position + 1})
    
    # ATTENZIONE: Questo sovrascrive field_choices con una nuova lista contenente solo new_choice.
    # Se l'intento è AGGIUNGERE la scelta alla lista esistente, la riga sotto è errata.
    # Dovrebbe essere field_choices.append(new_choice) e poi passare la lista aggiornata.
    # Ho commentato la riga originale e aggiunto quella corretta per chiarezza.
    # field_choices = [] # Rimuovi o commenta questa riga se vuoi aggiungere alla lista esistente
    # field_choices.append(new_choice) # Questa riga dovrebbe essere usata per aggiungere

    # Per mantenere la logica che sembra essere stata tentata, ma con un fix:
    # Creiamo una nuova lista che include le scelte originali e la nuova.
    # Se field_choices è None o vuoto all'inizio di questa funzione,
    # la logica sopra calcola max_position su una lista vuota, il che è corretto.
    # Poi aggiungiamo la nuova scelta alla lista.
    
    # Assicuriamoci che field_choices sia una lista valida per l'append.
    if not isinstance(field_choices, list):
        field_choices = []
    
    # Crea una copia per evitare modifiche in-place indesiderate se field_choices è passato per riferimento
    updated_choices_list = list(field_choices)
    updated_choices_list.append(new_choice)

    updated_field = {}
    updated_field.update({"label": field["label"]})
    updated_field.update({"choices": updated_choices_list}) # Usa la lista aggiornata
    return updated_field


def freshdesk_update_field(field_id: int, field: dict):
    log.info("[yellow]Updating Freshdesk Field " + str(field))
    url = f"https://{freshdesk_url}/api/v2/admin/ticket_fields/{field_id}"
    headers, auth = freshdesk_headers()
    response = requests.put(url=url, headers=headers, json=field, auth=auth)
    if response.status_code == 200:
        log.info(f"[green]Campo Freshdesk '{field.get('label', 'Sconosciuto')}' aggiornato con successo.")
        return json.loads(response.content)
    else:
        log.error(f"[red]Errore nell'aggiornamento del campo Freshdesk '{field.get('label', 'Sconosciuto')}': {response.reason}")
        log.error(f"[red]Codice di stato: {response.status_code}")
        log.error(f"[red]Contenuto risposta: {response.text}")
        return None # Importante: restituisce None in caso di errore


def freshdesk_resolve_priority(priority: str, fields: dict):
    # Aggiunto controllo per None su freshdesk_view_field
    field_response = freshdesk_view_field(field_name="priority", fields=fields)
    if field_response is None:
        log.error("[red]Impossibile risolvere la priorità: campo 'priority' non trovato o errore nel recupero.")
        return priority # Restituisce la priorità originale o un valore di default
    
    field_choices = freshdesk_get_field_choices(response=field_response)
    # Aggiunto controllo per gestire il caso in cui 'next' non trovi corrispondenze
    try:
        return next(ch for ch in field_choices if ch["value"] == priority)["label"]
    except StopIteration:
        log.warning(f"[yellow]Priorità '{priority}' non trovata tra le scelte del campo Freshdesk.")
        return priority # Restituisce la priorità originale se non trovata


def freshdesk_get_tickets(repo: str):
    log.info("[yellow]Getting Freshdesk Tickets")
    url = (
        "https://"
        + freshdesk_url
        + '/api/v2/search/tickets?query="(status:<3 OR status:>6) AND tag:'
        + "'"
        + tag
        + "'"
        + " AND cf_repository:"
        + "'"
        + repo
        + "'"
        + '"'
    )
    headers, auth = freshdesk_headers()
    response = requests.get(url=url, headers=headers, auth=auth)
    if response.status_code == 200:
        tickets = json.loads(response.content)["results"]
        log.info("[green]Freshdesk Tickets found: " + str(len(tickets)))
        return tickets
    else:
        log.error(f"[red]Errore nel recupero dei ticket Freshdesk: {response.reason}")
        log.error(f"[red]Codice di stato: {response.status_code}")
        log.error(f"[red]Contenuto risposta: {response.content.decode('utf-8')}")
        return [] # Restituisce una lista vuota in caso di errore


def freshdesk_get_ticket_summary(ticket: dict):
    log.info(f"[yellow]Getting Freshdesk Ticket Summary per ticket ID: {ticket['id']}")
    url = (
        "https://" + freshdesk_url + "/api/v2/tickets/" + str(ticket["id"]) + "/summary"
    )
    headers, auth = freshdesk_headers()
    response = requests.get(url=url, headers=headers, auth=auth)
    if response.status_code == 200:
        summary = json.loads(response.content)["body"]
        log.info("[green]Freshdesk Ticket Summary found")
        ticket.update({"summary": summary})
        return ticket
    else:
        log.error(f"[red]Errore nel recupero del summary del ticket {ticket['id']}: {response.reason}")
        log.error(f"[red]Codice di stato: {response.status_code}")
        log.error(f"[red]Contenuto risposta: {response.content.decode('utf-8')}")
        ticket.update({"summary": ""})
        return ticket


def freshdesk_update_ticket_ghissue(ticket: dict, gh_issue: dict):
    updated_ticket = {}
    new_issue_number = {"cf_github_issue": str(gh_issue["number"])}
    updated_ticket.update({"custom_fields": new_issue_number})
    if updated_ticket != {}:
        log.info(
            "[yellow]Updating Freshdesk Ticket "
            + str(ticket["id"])
            + " "
            + str(updated_ticket)
        )
        url = f"https://{freshdesk_url}/api/v2/tickets/{ticket["id"]}"
        headers, auth = freshdesk_headers()
        response = requests.put(
            url=url, headers=headers, json=updated_ticket, auth=auth
        )
        if response.status_code == 200:
            log.info(f"[green]Ticket Freshdesk {ticket['id']} aggiornato con Issue Github.")
            return json.loads(response.content)
        else:
            log.error(f"[red]Errore nell'aggiornamento del ticket Freshdesk {ticket['id']} con Issue Github: {response.reason}")
            log.error(f"[red]Codice di stato: {response.status_code}")
            log.error(f"[red]Contenuto risposta: {response.content.decode('utf-8')}")
            return None # Restituisce None in caso di errore


def freshdesk_add_note(gh_issue: dict, ticket_id, repo: str):
    log.info(f"[yellow]Posting Freshdesk Note per ticket ID: {ticket_id}")
    try:
        assignee = gh_issue["user"]["login"]
    except:
        assignee = ""
    new_note_text = f'<html><h2 style="color: red;">Github Notification</h2><p>{assignee} created <a href="{gh_issue["html_url"]}">#{gh_issue["number"]}</a> at {gh_issue["created_at"]} in <a href="{gh_issue["repository_url"]}">{repo}</a></p></html>'
    note = {}
    note.update({"body": new_note_text})
    note.update({"private": True})
    url = f"https://{freshdesk_url}/api/v2/tickets/{ticket_id}/notes"
    headers, auth = freshdesk_headers()
    response = requests.post(url=url, headers=headers, json=note, auth=auth)
    if response.status_code == 201:
        log.info(f"[green]Nota aggiunta al ticket Freshdesk {ticket_id}.")
        return json.loads(response.content)
    else:
        log.error(f"[red]Errore nell'aggiunta della nota al ticket Freshdesk {ticket_id}: {response.reason}")
        log.error(f"[red]Codice di stato: {response.status_code}")
        log.error(f"[red]Contenuto risposta: {response.content.decode('utf-8')}")
        return None # Restituisce None in caso di errore


def freshdesk_update_ticket_from_project(card: dict, ticket: dict):
    updated_ticket = {}
    try:
        new_ass = card["assignee"]
    except:
        new_ass = None
    if new_ass != ticket["custom_fields"]["cf_assigned_developer"]:
        if new_ass != None:
            new_ass = {"cf_assigned_developer": new_ass}
            updated_ticket.update({"custom_fields": new_ass})
    if card[status_field] != ticket["custom_fields"]["cf_development_status"]:
        new_status = {"cf_development_status": card[status_field]}
        updated_ticket.update({"custom_fields": new_status})
    try:
        new_date = card[iteration_field]
    except:
        new_date = None
    if new_date != ticket["custom_fields"]["cf_start_date"]:
        new_date = {"cf_start_date": new_date}
        updated_ticket.update({"custom_fields": new_date})
    try:
        new_date = card["iteration_end"]
    except:
        new_date = None
    if new_date != ticket["custom_fields"]["cf_end_date"]:
        new_date = {"cf_end_date": new_date}
        updated_ticket.update({"custom_fields": new_date})
    if updated_ticket != {}:
        log.info(
            "[yellow]Updating Freshdesk Ticket "
            + str(ticket["id"])
            + " "
            + str(updated_ticket)
        )
        url = f"https://{freshdesk_url}/api/v2/tickets/{ticket["id"]}"
        headers, auth = freshdesk_headers()
        response = requests.put(
            url=url, headers=headers, json=updated_ticket, auth=auth
        )
        if response.status_code == 200:
            log.info(f"[green]Ticket Freshdesk {ticket['id']} aggiornato dal progetto.")
            return json.loads(response.content)
        else:
            log.error(f"[red]Errore nell'aggiornamento del ticket Freshdesk {ticket['id']} dal progetto: {response.reason}")
            log.error(f"[red]Codice di stato: {response.status_code}")
            log.error(f"[red]Contenuto risposta: {response.content.decode('utf-8')}")
            return None # Restituisce None in caso di errore


def get_create_fields(repos: dict):
    fields = freshdesk_get_fields()
    github_project_fields = github_get_project_fields()

    # Gestione del campo 'Task Title'
    if not next(
        (field for field in fields if field["name"] == "cf_development_task_title"),
        False,
    ):
        log.info("[yellow]Campo 'Task Title' non trovato, tentativo di creazione.")
        field = {
            "label": "Task Title",
            "label_for_customers": "Task Title",
            "type": "custom_text",
            "customers_can_edit": False,
            "required_for_closure": False,
            "required_for_agents": False,
            "required_for_customers": False,
            "displayed_to_customers": True,
        }
        freshdesk_create_field(field=field)
    else:
        log.info("[green]Campo 'Task Title' già esistente.")


    # Gestione del campo 'Github Issue'
    if not next(
        (field for field in fields if field["name"] == "cf_github_issue"), False
    ):
        log.info("[yellow]Campo 'Github Issue' non trovato, tentativo di creazione.")
        field = {
            "label": "Github Issue",
            "label_for_customers": "Github Issue",
            "type": "custom_text",
            "customers_can_edit": False,
            "required_for_closure": False,
            "required_for_agents": False,
            "required_for_customers": False,
            "displayed_to_customers": False,
        }
        freshdesk_create_field(field=field)
    else:
        log.info("[green]Campo 'Github Issue' già esistente.")

    # Gestione del campo 'Assigned Developer'
    assigned_developer_field_exists = next(
        (field for field in fields if field["name"] == "cf_assigned_developer"), False
    )
    
    field_response_assigned_dev = None
    if not assigned_developer_field_exists:
        log.info("[yellow]Campo 'Assigned Developer' non trovato, tentativo di creazione.")
        field = {
            "label": "Assigned Developer",
            "label_for_customers": "Assigned Developer",
            "type": "custom_dropdown",
            "choices" : 
                [
                    {"value":"user1","position":1}
                ],
            "customers_can_edit": False,
            "required_for_closure": False,
            "required_for_agents": False,
            "required_for_customers": False,
            "displayed_to_customers": False,
        }
        field_response_assigned_dev = freshdesk_create_field(field)
    else:
        log.info("[green]Campo 'Assigned Developer' già esistente, recupero informazioni.")
        field_response_assigned_dev = freshdesk_view_field(
            field_name="cf_assigned_developer", fields=fields
        )

    if field_response_assigned_dev: # Procedi solo se field_response_assigned_dev non è None
        field_id_assigned_dev = field_response_assigned_dev["id"]
        field_choices_assigned_dev = freshdesk_get_field_choices(response=field_response_assigned_dev)
        members = github_get_members()
        updated_field_assigned_dev = None
        for member in members:
            if not freshdesk_field_choice_exists(
                field_choices=field_choices_assigned_dev, choice=member
            ):
                updated_field_assigned_dev = freshdesk_add_field_choice(
                    field=field_response_assigned_dev, field_choices=field_choices_assigned_dev, new_value=member
                )
        if updated_field_assigned_dev:
            freshdesk_update_field(field_id=field_id_assigned_dev, field=updated_field_assigned_dev)
    else:
        log.error("[red]Impossibile procedere con 'Assigned Developer': campo non creato o recuperato.")


    # Gestione del campo 'Development Status'
    development_status_field_exists = next(
        (field for field in fields if field["name"] == "cf_development_status"), False
    )

    field_response_dev_status = None
    if not development_status_field_exists:
        log.info("[yellow]Campo 'Development Status' non trovato, tentativo di creazione.")
        field = {
            "label": "Development Status",
            "label_for_customers": "Development Status",
            "type": "custom_dropdown",
            "choices" : 
                [
                    {"label": "user1", "value":"user1","position":1}
                ],
            "customers_can_edit": False,
            "required_for_closure": False,
            "required_for_agents": False,
            "required_for_customers": False,
            "displayed_to_customers": False,
        }
        field_response_dev_status = freshdesk_create_field(field)
    else:
        log.info("[green]Campo 'Development Status' già esistente, recupero informazioni.")
        field_response_dev_status = freshdesk_view_field(
            field_name="cf_development_status", fields=fields
        )

    if field_response_dev_status: # Procedi solo se field_response_dev_status non è None
        field_id_dev_status = field_response_dev_status["id"]
        field_choices_dev_status = freshdesk_get_field_choices(response=field_response_dev_status)
        statuses = github_get_project_statuses(github_project_fields)
        updated_field_dev_status = None
        
        # Correggi la logica di freshdesk_add_field_choice per aggiungere correttamente le scelte
        current_choices_for_update = list(field_choices_dev_status) # Inizia con le scelte attuali
        
        for status in statuses:
            if not freshdesk_field_choice_exists(
                field_choices=current_choices_for_update, choice=status
            ):
                # Aggiungi la nuova scelta alla lista temporanea
                max_position = 0
                if current_choices_for_update:
                    max_position = max(c.get("position", 0) for c in current_choices_for_update)
                
                new_choice = {
                    "label": status,
                    "value": status,
                    "position": max_position + 1
                }
                current_choices_for_update.append(new_choice)
                updated_field_dev_status = { # Prepara l'oggetto per l'aggiornamento
                    "label": field_response_dev_status["label"],
                    "choices": current_choices_for_update
                }
        
        if updated_field_dev_status: # Se ci sono state aggiunte, aggiorna il campo
            freshdesk_update_field(field_id=field_id_dev_status, field=updated_field_dev_status)
    else:
        log.error("[red]Impossibile procedere con 'Development Status': campo non creato o recuperato.")


    # Gestione del campo 'Repository'
    repository_field_exists = next(
        (field for field in fields if field["name"] == "cf_repository"), False
    )

    field_response_repo = None
    if not repository_field_exists:
        log.info("[yellow]Campo 'Repository' non trovato, tentativo di creazione.")
        field = {
            "label": "Repository",
            "label_for_customers": "Repository",
            "type": "custom_dropdown",
            "choices" : 
                [
                    {"value":"user1","position":1}
                ],
            "customers_can_edit": False,
            "required_for_closure": False,
            "required_for_agents": False,
            "required_for_customers": False,
            "displayed_to_customers": False,
        }
        # ATTENZIONE: Qui c'era un errore, passava updated_field invece di field
        field_response_repo = freshdesk_create_field(field) 
    else:
        log.info("[green]Campo 'Repository' già esistente, recupero informazioni.")
        field_response_repo = freshdesk_view_field(field_name="cf_repository", fields=fields)

    if field_response_repo: # Procedi solo se field_response_repo non è None
        field_id_repo = field_response_repo["id"]
        field_choices_repo = freshdesk_get_field_choices(response=field_response_repo)
        
        current_choices_for_update_repo = list(field_choices_repo) # Inizia con le scelte attuali
        updated_field_repo = None # Reset dell'updated_field per questo blocco
        
        for repo_name in repos: # Rinominato 'repo' in 'repo_name' per evitare shadowing
            if not freshdesk_field_choice_exists(field_choices=current_choices_for_update_repo, choice=repo_name):
                max_position = 0
                if current_choices_for_update_repo:
                    max_position = max(c.get("position", 0) for c in current_choices_for_update_repo)
                
                new_choice = {
                    "label": repo_name,
                    "value": repo_name,
                    "position": max_position + 1
                }
                current_choices_for_update_repo.append(new_choice)
                updated_field_repo = { # Prepara l'oggetto per l'aggiornamento
                    "label": field_response_repo["label"],
                    "choices": current_choices_for_update_repo
                }
        
        if updated_field_repo: # Se ci sono state aggiunte, aggiorna il campo
            freshdesk_update_field(field_id=field_id_repo, field=updated_field_repo)
    else:
        log.error("[red]Impossibile procedere con 'Repository': campo non creato o recuperato.")


    # Gestione del campo 'Start Date'
    if not next((field for field in fields if field["name"] == "cf_start_date"), False):
        log.info("[yellow]Campo 'Start Date' non trovato, tentativo di creazione.")
        field = {
            "label": "Start Date",
            "label_for_customers": "Start Date",
            "type": "custom_date",
            "customers_can_edit": False,
            "required_for_closure": False,
            "required_for_agents": False,
            "required_for_customers": False,
            "displayed_to_customers": True,
        }
        freshdesk_create_field(field=field)
    else:
        log.info("[green]Campo 'Start Date' già esistente.")

    # Gestione del campo 'End Date'
    if not next((field for field in fields if field["name"] == "cf_end_date"), False):
        log.info("[yellow]Campo 'End Date' non trovato, tentativo di creazione.")
        field = {
            "label": "End Date",
            "label_for_customers": "End Date",
            "type": "custom_date",
            "customers_can_edit": False,
            "required_for_closure": False,
            "required_for_agents": False,
            "required_for_customers": False,
            "displayed_to_customers": True,
        }
        freshdesk_create_field(field=field)
    else:
        log.info("[green]Campo 'End Date' già esistente.")

    return fields, github_project_fields


def create_update_github_issues(fd_fields, gh_fields: dict, repo: str, cards: dict):
    log.info("[green]Starting sync for Repository " + repo)
    tickets = freshdesk_get_tickets(repo)
    for t in tickets:
        t = freshdesk_get_ticket_summary(t)
        if t["custom_fields"]["cf_github_issue"] == None:
            if (t["custom_fields"]["cf_development_task_title"] != None) and (
                t["custom_fields"]["cf_repository"] != None
            ):
                gh_issue = github_create_issue(t, repo)
                if gh_issue != {}: # Controlla se l'issue è stata creata con successo
                    freshdesk_update_ticket_ghissue(ticket=t, gh_issue=gh_issue)
                    freshdesk_add_note(gh_issue=gh_issue, ticket_id=t["id"], repo=repo)
        else:
            gh_issue = github_get_issue(t["custom_fields"]["cf_github_issue"], repo)
            if gh_issue: # Controlla se l'issue Github è stata recuperata
                card = next(
                    (
                        c
                        for c in cards
                        if (c["issue_number"] == gh_issue["number"])
                        and (c["repository"] == repo)
                    ),
                    False,
                )
                if card: # Controlla se la card del progetto è stata trovata
                    newcard = github_update_issue(t, gh_issue, repo, card)
                    # Assicurati che newcard non sia None prima di procedere
                    if newcard:
                        github_update_project_card(
                            card=newcard,
                            company=freshdesk_get_company_name(ticket=t),
                            priority=freshdesk_resolve_priority(
                                t["priority"], fields=fd_fields
                            ),
                            fields=gh_fields,
                        )
                        freshdesk_update_ticket_from_project(card=newcard, ticket=t)
    log.info("[green]Ending sync for Repository " + repo)


if __name__ == "__main__":
    repos = github_get_repos()
    cards = github_get_project_cards()
    fd_fields, gh_fields = get_create_fields(repos)
    # Aggiunto controllo per assicurarsi che i campi siano stati recuperati/creati correttamente
    if fd_fields is None or gh_fields is None:
        log.error("[red]Errore critico: Impossibile recuperare o creare i campi Freshdesk/Github. Uscita.")
        exit(1) # Termina lo script con un codice di errore
        
    for repo in repos:
        create_update_github_issues(fd_fields, gh_fields, repo, cards)
