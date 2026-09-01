"""Business-logic services, kept separate from UI/CLI code. Deliberately
has no re-exports here so importing e.g. face_matching doesn't drag in
cv2/insightface for modules that don't need them."""
