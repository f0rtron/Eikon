from core.register import register_student, RegistrationSession
from core.train import train, load_encodings
from core.face_engine import get_engine, get_embedding, cosine_similarity
from core.anti_spoof import AntiSpoof, get_spoof_checker
from core.recognize import RecognitionEngine, FaceResult
