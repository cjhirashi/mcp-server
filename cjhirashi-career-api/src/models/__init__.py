"""
cjhirashi-career ORM Models
SQLAlchemy models for all database entities.
"""
# Core Models
from models.user import User

# ----------------------------------------------------------------------------
# Career Domain (v2) - 31 tables
# ----------------------------------------------------------------------------

# Dominio 1: Identidad Profesional
from models.personal_profile import PersonalProfile
from models.differentiator import Differentiator
from models.identity import Identity
from models.identity_reflection import IdentityReflection
from models.competencies import Competency
from models.certification import Certification
from models.target_role import TargetRole
from models.work_history import WorkHistory
from models.achievement import Achievement
from models.star_story import StarStory
from models.career_review import CareerReview
from models.role_gap_analysis import RoleGapAnalysis
from models.project import Project

# Dominio 2: Operativa de Búsqueda
from models.fit_scoring_factor import FitScoringFactor
from models.market_segment import MarketSegment
from models.role_narrative import RoleNarrative
from models.search_plan import SearchPlan
from models.networking_contact import NetworkingContact
from models.target_company import TargetCompany
from models.vacancy import Vacancy
from models.cv_version import CVVersion
from models.cover_letter_version import CoverLetterVersion
from models.application import Application
from models.application_interaction import ApplicationInteraction
from models.interview import Interview
from models.contact_interaction import ContactInteraction
from models.networking_activity import NetworkingActivity

# Dominio 3: Presencia Digital
from models.publication import Publication
from models.linkedin_profile import LinkedInProfile
from models.github_profile import GitHubProfile
from models.portal_home import PortalHome
from models.portal_about import PortalAbout
from models.portal_contact import PortalContact

# Dominio 4: Soporte
from models.tag import Tag

# Dominio 5: Metodologías Operativas
from models.operational_methodology import OperationalMethodology

# Agent Bedrock
from models.bedrock_usage_log import BedrockUsageLog
from models.bedrock_usage_round_log import BedrockUsageRoundLog
from models.bedrock_settings import BedrockSettings
from models.bedrock_agent_profile_prompt import BedrockAgentProfilePrompt
from models.bedrock_agent_profile_photo import BedrockAgentProfilePhoto
from models.bedrock_agent_delegation import BedrockAgentDelegation
from models.bedrock_agent_profile_tool import BedrockAgentProfileTool
from models.admin_section_override import AdminSectionOverride
from models.bedrock_custom_tool import BedrockCustomTool
from models.bedrock_conversation import BedrockConversation, BedrockConversationMessage
from models.bedrock_task import BedrockTask
from models.user_notification import UserNotification
from models.error_report import ErrorReport
from models.pdf_output_template import PdfOutputTemplate
from models.pdf_template_style import PdfTemplateStyle

# ----------------------------------------------------------------------------
# LinkedIn Integration
# ----------------------------------------------------------------------------

from models.linkedin_connection import LinkedInConnection
from models.linkedin_post import LinkedInPost

# ----------------------------------------------------------------------------
# Base System (v1) - unchanged
# ----------------------------------------------------------------------------

# Security & Authentication
from models.refresh_token import RefreshToken

# File Management
from models.file_upload import FileUpload, FileType

# Analytics & Tracking
from models.event import Event, EventType
from models.audit_log import AuditLog, AuditAction
from models.metrics import Metrics
from models.user_session import UserSession

__all__ = [
    # Core
    "User",
    # Identity domain
    "PersonalProfile",
    "Differentiator",
    "Identity",
    "IdentityReflection",
    "Competency",
    "Certification",
    "TargetRole",
    "WorkHistory",
    "Achievement",
    "StarStory",
    "CareerReview",
    "RoleGapAnalysis",
    "Project",
    # Search domain
    "FitScoringFactor",
    "MarketSegment",
    "RoleNarrative",
    "SearchPlan",
    "NetworkingContact",
    "TargetCompany",
    "Vacancy",
    "CVVersion",
    "CoverLetterVersion",
    "Application",
    "ApplicationInteraction",
    "Interview",
    "ContactInteraction",
    "NetworkingActivity",
    # Digital presence domain
    "Publication",
    "LinkedInProfile",
    "GitHubProfile",
    "PortalHome",
    "PortalAbout",
    "PortalContact",
    # Support domain
    "Tag",
    # Operational methodologies domain
    "OperationalMethodology",
    # Agent Bedrock
    "BedrockUsageLog",
    "BedrockUsageRoundLog",
    "BedrockSettings",
    "BedrockAgentProfilePrompt",
    "BedrockAgentProfilePhoto",
    "BedrockAgentDelegation",
    "BedrockAgentProfileTool",
    "AdminSectionOverride",
    "BedrockCustomTool",
    "BedrockConversation",
    "BedrockConversationMessage",
    "BedrockTask",
    "UserNotification",
    "ErrorReport",
    "PdfOutputTemplate",
    "PdfTemplateStyle",
    # LinkedIn integration
    "LinkedInConnection",
    "LinkedInPost",
    # Security
    "RefreshToken",
    # Files
    "FileUpload",
    "FileType",
    # Analytics
    "Event",
    "EventType",
    "AuditLog",
    "AuditAction",
    "Metrics",
    "UserSession",
]
