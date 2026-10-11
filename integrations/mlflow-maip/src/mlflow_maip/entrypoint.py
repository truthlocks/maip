"""Lazy entry point: MLflow can discover the plugin while importing itself."""

def create_store(store_uri, artifact_uri=None):
    from .plugin import MAIPTrackingStore
    return MAIPTrackingStore(store_uri, artifact_uri)
