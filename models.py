from typing import Literal, get_args
from sqlalchemy import ForeignKey, Enum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, backref


def model_to_dict(model_obj):
    data = {}
    for column in model_obj.__table__.columns:
        data[column.name] = getattr(model_obj, column.name)
    return data


class Base(DeclarativeBase):
    pass


class Workflow(Base):
    __tablename__ = 'workflow'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]

    nodes: Mapped[list['Node']] = relationship(back_populates='workflow', cascade="all, delete")


class Node(Base):
    __tablename__ = 'node'

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[int] = mapped_column(ForeignKey('workflow.id'))
    workflow: Mapped[Workflow] = relationship(back_populates='nodes')
    type: Mapped[str]

    __mapper_args__ = {
        'polymorphic_identity': 'node',
        'polymorphic_on': 'type'
    }


class Edge(Base):
    __tablename__ = 'edge'

    out_id: Mapped[int] = mapped_column(ForeignKey('node.id'), primary_key=True)
    in_id: Mapped[int] = mapped_column(ForeignKey('node.id'), primary_key=True)
    label: Mapped[str] = mapped_column(default='', primary_key=True)

    out_node = relationship(
        Node, primaryjoin=out_id == Node.id, backref=backref('out_edges', cascade='all, delete')
    )

    in_node = relationship(
        Node, primaryjoin=in_id == Node.id, backref=backref('in_edges', cascade='all, delete')
    )


class StartNode(Node):
    __tablename__ = 'startnode'

    id: Mapped[int] = mapped_column(ForeignKey('node.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': 'startnode'
    }


class EndNode(Node):
    __tablename__ = 'endnode'

    id: Mapped[int] = mapped_column(ForeignKey('node.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': 'endnode'
    }


NodeStatus = Literal['pending', 'sent', 'opened']


class MessageNode(Node):
    __tablename__ = 'messagenode'

    id: Mapped[int] = mapped_column(ForeignKey('node.id'), primary_key=True)
    status: Mapped[NodeStatus] = mapped_column(Enum(
        *get_args(NodeStatus),
        name='nodestatus',
        create_constraint=True,
        validate_strings=True
    ))
    text: Mapped[str]

    __mapper_args__ = {
        'polymorphic_identity': 'messagenode'
    }


class ConditionNode(Node):
    __tablename__ = 'conditionnode'

    id: Mapped[int] = mapped_column(ForeignKey('node.id'), primary_key=True)
    condition: Mapped[str]

    __mapper_args__ = {
        'polymorphic_identity': 'conditionnode'
    }
