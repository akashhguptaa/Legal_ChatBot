from utils.dataBase_integration import process_query_search
from loguru import logger
from utils.dataBase_integration import embeddings_model
from utils.dataBase_integration import search_similar_sections, embeddings_collection

# def call_process_search_query(query, file_id):
#     """
#     Calls the process_search_query function from utils.database_integration.

#     Args:
#         query (str): The search query string.

#     Returns:
#         Any: The result from process_search_query.
#     """
#     result = process_query_search(query, file_id)
#     print(result["answer"])
#     return result
# # call_process_search_query("what is in this document ", "dbd4cc47-3d3f-4df8-a662-2c694af00928")

# def test_llm(query: str, file_id: str):
#     """Test function to demonstrate the use of embeddings and vector search.
#     """
#     query_embedding = embeddings_model.embed_query(query)
#             # We can get more results here to give the LLM more context.
#     logger.info(f"RAG Pipeline: Query embedding generated for query: {query}")
#     relevant_sections = search_similar_sections(
#         query_embedding=query_embedding,
#             file_id=file_id,
#             limit=5  # Get the top 5 most relevant sections
#         )
#     if not relevant_sections:
#         logger.warning("RAG Pipeline: No relevant sections found in vector search.")
#         logger.info("RAG Pipeline: Falling back to semantic search.")

# # test_llm("What is in this document?", "dbd4cc47-3d3f-4df8-a662-2c694af00928")

# # Add this after your existing index creation code
# try:
#     # Create vector search index if it doesn't exist
#     index_exists = False
#     for index in embeddings_collection.list_indexes():
#         if index.get('name') == 'vector_index':
#             index_exists = True
#             break
            
#     if not index_exists:
#         embeddings_collection.create_index(
#             [("embedding", "vector")],
#             name="vector_index",
#             vectorOptions={
#                 "type": "vector",
#                 "dimensions": 1536,  # Must match your embedding dimensions
#                 "similarity": "cosine"  # Or "euclidean"/"dotProduct"
#             }
#         )
#         logger.info("Vector search index created successfully")
#     else:
#         logger.info("Vector search index already exists")
# except Exception as e:
#     logger.error(f"Error creating vector index: {e}")

# # Check if any documents have embeddings
# count_with_embeddings = embeddings_collection.count_documents({"embedding": {"$exists": True}})
# logger.info(f"Documents with embeddings: {count_with_embeddings}")

# # Count embeddings for the specific file_id
# file_id = "dbd4cc47-3d3f-4df8-a662-2c694af00928"
# count = embeddings_collection.count_documents({"file_id": file_id})

# print(f"Number of embeddings for document {file_id}: {count}")

# # Optional: Get a sample of the embeddings to verify their structure
# sample_embedding = embeddings_collection.find_one(
#     {"file_id": file_id}, 
#     {"embedding": 1, "section_title": 1, "section_index": 1}
# )
# import json
# print("\nSample embedding document:")
# print(sample_embedding)

# Check if embeddings exist for your file
file_id = "dbd4cc47-3d3f-4df8-a662-2c694af00928"
docs_with_embeddings = embeddings_collection.count_documents({
    "file_id": file_id,
    "embedding": {"$exists": True, "$ne": None}
})
print(f"Documents with actual embeddings: {docs_with_embeddings}")

index_exists = False
for index in embeddings_collection.list_indexes():
    print(index)  # Log all indexes to check
    if index.get('name') == 'vector_index':
        index_exists = True
        print("Vector index found! Details:", index)
        break

if not index_exists:
    print("❌ Vector index missing. Creating now...")
    embeddings_collection.create_index(
        [("embedding", "vector")],
        name="vector_index",
        vectorOptions={
            "type": "vector",
            "dimensions": 1536,  # Must match OpenAI's embedding size
            "similarity": "cosine",
        }
    )
    print("✅ Vector index created.")
else:
    print("✅ Vector index already exists.")