from spacy.tokens import Token
from privacy_policy_analyzer import utils

Token.set_extension("src", getter=utils.token_to_source)
Token.set_extension("ent", getter=utils.token_to_ent)
