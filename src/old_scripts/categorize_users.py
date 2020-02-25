import requests
import json
import time
from pymongo import MongoClient
from timeit import default_timer as timer

MONGO_CLIENT_STRING = "mongodb+srv://jek248:SentimentAnalysis@sentiment-analysis-8snlg.mongodb.net/test?retryWrites=true&w=majority"
GITHUB_AUTHORIZATION_KEY = "token cada15847aab7e8a14fdc38216c5e618e89ed708"
GITHUB_GRAPHQL_ENDPOINT = "https://api.github.com/graphql"
HTTP_OK_RESPONSE = 200
DAY_IN_SECONDS = 86400
HOUR_IN_SECONDS = 3600
HEADERS = {"Authorization": GITHUB_AUTHORIZATION_KEY}

def setup_repo_query(repo_owner: str, repo_name: str, end_cursor: str = "") -> str:
    query = f"""
    query {{
    repository(owner: "{repo_owner}", name: "{repo_name}") {{
        nameWithOwner
        pullRequests(first: 100{end_cursor}) {{
        totalCount
        pageInfo {{
            endCursor
            hasNextPage
        }}
        nodes {{
            number
            author {{
            login
            }}
            authorAssociation
            bodyText
        }}
        }}
    }}
    }}
    """
    return query

def setup_user_query(pr_author: str, end_cursor: str="") -> str:
    query = f"""
    query {{
    user(login: "{pr_author}") {{
        pullRequests(first: 1{end_cursor}) {{
            totalCount
        }}
    }}
    }}
    """
    return query

def run_query(query: str) -> json:
    # Created session to avoid timeout errors
    with requests.Session().post(GITHUB_GRAPHQL_ENDPOINT, json={"query":query}, headers=HEADERS) as response:
        if response.status_code == HTTP_OK_RESPONSE:
            return response.json()
        #else:
        #raise Exception(f'ERROR [{response.status_code}]: Query failed to execute: {query}\nRESPONSE: {response.text}')

def collect_prs_from_repos_in_db(client: MongoClient) -> None:
    # Gather collection names frmo repositories database
    repo_db = client["repositories"]
    # collection_names = repo_db.list_collection_names()

    # Create a query for each repo
    collection = repo_db["collect_mnst1000_mxst10000_lsact90_crtd1456_nmpll100"]

    # Grabs all the documents in the cursor to avoid a cursor timeout
    documents_in_collection = [document for document in collection.find()]

    for document in documents_in_collection:
        # Variables that assist with collecting data
        end_cursor = ""
        end_cursor_string = ""
        has_next_page = True
        list_of_query_data = list()
        pull_request_data = dict()
    
        repo_name = document["name"]
        repo_owner = document["owner"]
        name_with_owner = f"{repo_owner}/{repo_name}"
        pull_request_data[name_with_owner] = list()
        print(f"[WORKING] Gathering PRs from: {repo_owner}/{repo_name}")

        # Iterates through all the valid pull requests
        while has_next_page:
            query = setup_repo_query(repo_owner, repo_name, end_cursor_string)
            query_data = run_query(query)
            has_next_page = query_data["data"]["repository"]["pullRequests"]["pageInfo"]["hasNextPage"]
            if has_next_page:
                end_cursor = query_data["data"]["repository"]["pullRequests"]["pageInfo"]["endCursor"]
                end_cursor_string = f', after:"{end_cursor}"'

            # Adds the data in a dictionary of lists 
            pull_request_data[name_with_owner].extend(query_data["data"]["repository"]["pullRequests"]["nodes"])
            
        total_count = query_data["data"]["repository"]["pullRequests"]["totalCount"]

        # If we collected the PRs insert it into MongoDB
        if total_count == len(pull_request_data[name_with_owner]):
            print(f"[WORKING][SUCCESS] Gathered {len(pull_request_data[name_with_owner])}/{total_count} from {name_with_owner}\n")
        else:
            print(f"[WORKING][ERROR] Could not gather all PRs. Gathered only {len(list_of_query_data)}/{total_count}\n")

        # Inserts all the PRs in MongoDB 
        database = client["ALL_PRS_BY_REPO"]
        collections = database[name_with_owner]
        collections.insert_many(pull_request_data[name_with_owner])

def categorize_users(client: MongoClient, periphery_max=10, core_max=100) -> None:
    print(f"[WORKING] Categorizing users...\n[WORKING] Max PRs for Periphery: {periphery_max}\n[WORKING] Max PRs for Core: {core_max}")

    print(f"[WORKING] Categorizing core...")
    categorize_core(client, core_max)

    print(f"[WORKING] Categorizing peripheries...")
    categorize_periphery(client, periphery_max)

def categorize_core(client:MongoClient, core_max=100) -> None:
    pass

def categorize_periphery(client: MongoClient, periphery_max=10) -> None:
    pass

def collect_author_info(client: MongoClient) -> None:
    # Gets all the repositories's pull request's
    prs_by_repo_database = client["ALL_PRS_BY_REPO"]
    collection_names = prs_by_repo_database.list_collection_names()

    # Gets all the repositories already mined
    author_info_db = client["AUTHOR_INFO_BY_REPO_2"]
    collections_already_mined = author_info_db.list_collection_names()

    # Remove the repositories already mined
    for collection in collections_already_mined:
        collection_names.remove(collection)
        

    # Iterates through each repo
    for collection_name in collection_names:
        collection = prs_by_repo_database[collection_name]
        mined_authors = set()
        author_info = list()

        # Grabs all PRs and stores in a list to avoid cursor timeout
        documents_in_collection = [document for document in collection.find({})]

        for document in documents_in_collection:
            author = document["author"]
            author_association = document["authorAssociation"]
            body_text = document["bodyText"]

            # If the author exists/is not a ghost user
            if author is not None:
                author_login = author["login"]

                if author_login not in mined_authors:
                    print(f"[WORKING] Collecting {author_login}'s author info for: {collection_name}...")
                    mined_authors.add(author_login)

                    # Grabs the total amount of pull requests for the repository
                    search_query = {"author": {"login": f"{author_login}"}}
                    pull_requests_by_user = [pull_request for pull_request in collection.find(search_query)]
                    repo_pr_count = len(pull_requests_by_user)

                    # Gets the total amount of PRs for each user
                    user_query = setup_user_query(author_login)
                    user_data = run_query(user_query)

                    # Gather's the total PR count from user_data
                    try:
                        # Checks if user data is valiFd
                        if user_data is not None and user_data["data"] is not None and user_data["data"]["user"] is not None and user_data["data"]["user"]["pullRequests"] is not None:
                            total_pr_count = user_data["data"]["user"]["pullRequests"]["totalCount"]

                            print(f"[WORKING] {author_login} contributed {repo_pr_count}/{total_pr_count} pull requests to: {collection_name}\n")
                            author_info.append({
                                    "author": author_login,
                                    "association": author_association,
                                    "total_for_repo": repo_pr_count,
                                    "total_overall": total_pr_count,
                                    "bodyText" : body_text
                                })
                        else: print("AUTHOR IS NOT VALID")
                    except KeyError:
                        # Error handling for RATE_LIMIT_EXCEEDED for GitHub GraphQL API
                        print(f"[WORKING] {user_data['errors'][0]['type']}: {user_data['errors'][0]['message']}, sleeping for {HOUR_IN_SECONDS} seconds...")
                        time.sleep(HOUR_IN_SECONDS)
                        

        # Inserts author info into MongoDB
        collections = author_info_db[collection_name]
        collections.insert_many(author_info)

def main() -> None:    
    # Create queries from repo databse
    client = MongoClient(MONGO_CLIENT_STRING)
    ALL_PRS_BY_REPO = client["ALL_PRS_BY_REPO"]
    AUTHOR_INFO_BY_REPO = client["AUTHOR_INFO_BY_REPO_2"]
    
    # If database is empty gather's all the PRs for each Repo in the database
    if len(ALL_PRS_BY_REPO.list_collection_names()) == 0:
        print("[WORKING] ALL_PRS_BY_REPO collection is empty...\n[WORKING] Collecting all pull requests...")
        collect_prs_from_repos_in_db(client)
    else:
        print("[WORKING] Pull requests already mined, gathering author information...\n")

    # If we haven't collected all the author info for each repo
    if len(AUTHOR_INFO_BY_REPO.list_collection_names()) < len(ALL_PRS_BY_REPO.list_collection_names()):
        print("[WORKING] AUTHOR_INFO_BY_REPO collection is empty/incomplete...\n[WORKING] Collecting author information from pull requests\n")
        collect_author_info(client)
    else:
        print("[WORKING] Author information already parsed, categorizing users...\n")

    # Categorizing Users
    categorize_users(client)

if __name__ == "__main__":
    print("[STARTING] Running script...\n")
    start_time = timer()
    main()
    end_time = timer()
    print("\n[DONE] Script completed in: %4.3fs" % (end_time - start_time))
