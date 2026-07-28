"""Tool: manage_contact — add, update, delete, and search contacts."""
from typing import Optional, List

from sqlalchemy.orm import Session

from db.models import Contact
from tools.schemas import ManageContactInput, ManageContactOutput


def _generate_contact_id(db: Session) -> str:
    """Generate a unique contact ID like CNT-001."""
    existing = db.query(Contact).count()
    seq = existing + 1
    return "CNT-{:03d}".format(seq)


def _find_contact_by_id_or_name(
    db: Session,
    contact_id: Optional[str] = None,
    contact_name: Optional[str] = None,
) -> Optional[Contact]:
    """Find a contact by contact_id or contact_name."""
    if contact_id:
        return db.query(Contact).filter(Contact.contact_id == contact_id).first()
    if contact_name:
        return db.query(Contact).filter(Contact.contact_name == contact_name).first()
    return None


def manage_contact(
    input: ManageContactInput,
    db: Session,
) -> ManageContactOutput:
    """Manage contacts: add, update, delete, or search.

    - add: Creates a new contact, checking for duplicates first.
    - update: Finds by contact_id or contact_name and updates fields.
    - delete: Finds and deletes; raises ValueError if not found.
    - search: Finds contacts by partial name match, returns first 20 matches as message.
    """
    action = input.action.lower()

    if action == "add":
        # Check for duplicate
        existing = _find_contact_by_id_or_name(db, contact_name=input.contact_name)
        if existing is not None:
            raise ValueError(
                "Contact '{}' already exists with contact_id '{}'.".format(
                    input.contact_name, existing.contact_id
                )
            )

        contact_id = _generate_contact_id(db)
        contact = Contact(
            contact_id=contact_id,
            contact_name=input.contact_name,
            contact_type=input.contact_type,
            phone=input.phone,
            email=input.email,
            address=input.address,
            tax_id=input.tax_id,
        )
        db.add(contact)
        db.commit()
        db.refresh(contact)

        return ManageContactOutput(
            contact_id=contact.contact_id,
            contact_name=contact.contact_name,
            contact_type=contact.contact_type,
            action_performed="add",
            message="Contact '{}' created successfully.".format(contact.contact_name),
        )

    elif action == "update":
        contact = _find_contact_by_id_or_name(db, input.contact_id, input.contact_name)
        if contact is None:
            raise ValueError(
                "Contact with id '{}' or name '{}' not found.".format(
                    input.contact_id or "", input.contact_name or ""
                )
            )

        if input.contact_name is not None:
            contact.contact_name = input.contact_name
        if input.contact_type is not None:
            contact.contact_type = input.contact_type
        if input.phone is not None:
            contact.phone = input.phone
        if input.email is not None:
            contact.email = input.email
        if input.address is not None:
            contact.address = input.address
        if input.tax_id is not None:
            contact.tax_id = input.tax_id

        db.commit()
        db.refresh(contact)

        return ManageContactOutput(
            contact_id=contact.contact_id,
            contact_name=contact.contact_name,
            contact_type=contact.contact_type,
            action_performed="update",
            message="Contact '{}' updated successfully.".format(contact.contact_name),
        )

    elif action == "delete":
        contact = _find_contact_by_id_or_name(db, input.contact_id, input.contact_name)
        if contact is None:
            raise ValueError(
                "Contact with id '{}' or name '{}' not found — cannot delete.".format(
                    input.contact_id or "", input.contact_name or ""
                )
            )

        contact_name = contact.contact_name
        db.delete(contact)
        db.commit()

        return ManageContactOutput(
            contact_id=contact.contact_id,
            contact_name=contact_name,
            contact_type=contact.contact_type,
            action_performed="delete",
            message="Contact '{}' deleted successfully.".format(contact_name),
        )

    elif action == "search":
        pattern = "%{}%".format(input.contact_name)
        matches: List[Contact] = (
            db.query(Contact)
            .filter(Contact.contact_name.ilike(pattern))
            .limit(20)
            .all()
        )

        if not matches:
            return ManageContactOutput(
                contact_id="",
                contact_name=input.contact_name,
                contact_type=input.contact_type,
                action_performed="search",
                message="No contacts found matching '{}'.".format(input.contact_name),
            )

        names = [c.contact_name for c in matches]
        return ManageContactOutput(
            contact_id=matches[0].contact_id,
            contact_name=matches[0].contact_name,
            contact_type=matches[0].contact_type,
            action_performed="search",
            message="Found {} contact(s) matching '{}': {}".format(
                len(matches), input.contact_name, ", ".join(names)
            ),
        )

    else:
        raise ValueError("Invalid action '{}'. Must be add, update, delete, or search.".format(action))
