# Mendix Extensions API Reference
**Assembly:** `Mendix.StudioPro.ExtensionsAPI, Version=11.3.0.0, Culture=neutral, PublicKeyToken=null`

---

## Namespace: `Mendix.StudioPro.ExtensionsAPI`

### Classs


#### `ExtensionBase`

```csharp
public abstract class ExtensionBase
```


---

### Enums


#### `ServicesEnvironment`

```csharp
public enum ServicesEnvironment : IComparable, ISpanFormattable, IFormattable, IConvertible
```

**Enum Members**
```
None
Test
Acceptance
Production
```


---


#### `ThemeSupport`

```csharp
public enum ThemeSupport : IComparable, ISpanFormattable, IFormattable, IConvertible
```

**Enum Members**
```
Light
Dark
```


---

### Interfaces


#### `IConfiguration`

```csharp
public interface IConfiguration
```

**Properties**
```csharp
public ServicesEnvironment TargetServices { get; }
public ThemeSupport Theme { get; }
public string MendixVersion { get; }
public string EarliestSupportedLegacyMendixVersion { get; }
public string LatestSupportedLegacyMendixVersion { get; }
public string BuildTag { get; }
public CultureInfo CurrentLanguage { get; }
```


---


#### `IHttpClient`

```csharp
public interface IHttpClient : IDisposable
```

**Properties**
```csharp
public TimeSpan Timeout { get; set; }
```

**Methods**
```csharp
public Task`1 SendAsync(HttpRequestMessage request, CancellationToken cancellationToken);
```


---

## Namespace: `Mendix.StudioPro.ExtensionsAPI.BackgroundJobs`

### Classs


#### `BackgroundJob`

```csharp
public class BackgroundJob
```

**Properties**
```csharp
public string Title { get; }
public List`1 Steps { get; }
```

**Methods**
```csharp
public BackgroundJob AddStep(string title, string description, Func`1 function);
```


---


#### `BackgroundJobStep`

```csharp
public class BackgroundJobStep
```

**Properties**
```csharp
public string Title { get; }
public string Description { get; }
public Func`1 Function { get; }
```


---

## Namespace: `Mendix.StudioPro.ExtensionsAPI.ConsistencyCheck`

### Classs


#### `ConsistencyCheckExtension`1`

```csharp
public abstract class ConsistencyCheckExtension`1 : ExtensionBase, IConsistencyCheckExtension
```

**Methods**
```csharp
public IEnumerable`1 Check(TCheckedStructure structure, IModel model);
```


---


#### `ConsistencyError`

```csharp
public sealed class ConsistencyError
```

**Properties**
```csharp
public string Message { get; }
public IStructure ErrorSource { get; }
public string ErrorSourceDescription { get; }
public string ErrorSourceProperty { get; }
public Severity Severity { get; }
```


---

### Enums


#### `Severity`

```csharp
public enum Severity : IComparable, ISpanFormattable, IFormattable, IConvertible
```

**Enum Members**
```
Error
Warning
Deprecation
```


---

## Namespace: `Mendix.StudioPro.ExtensionsAPI.Drawing`

### Classs


#### `StudioProImage`

```csharp
public class StudioProImage
```


---

## Namespace: `Mendix.StudioPro.ExtensionsAPI.Model`

### Interfaces


#### `IAbstractUnit`

```csharp
public interface IAbstractUnit : IStructure
```

**Properties**
```csharp
public string Id { get; }
public IAbstractUnit Container { get; }
```


---


#### `IElement`

```csharp
public interface IElement : IStructure
```


---


#### `IModel`

```csharp
public interface IModel
```

**Properties**
```csharp
public IProject Root { get; }
```

**Methods**
```csharp
public T Create();
public T Copy(T source);
public IQualifiedName`1 ToQualifiedName(string fullName);
public bool TryGetAbstractUnitById(string abstractUnitId, IAbstractUnit& abstractUnit);
public ITransaction StartTransaction(string description);
```


---


#### `IQualifiedName`

```csharp
public interface IQualifiedName : IEquatable`1
```

**Properties**
```csharp
public string Name { get; }
public string FullName { get; }
```


---


#### `IQualifiedName`1`

```csharp
public interface IQualifiedName`1 : IQualifiedName, IEquatable`1
```

**Methods**
```csharp
public T Resolve();
```


---


#### `IReferableStructure`

```csharp
public interface IReferableStructure : IStructure
```


---


#### `IStructure`

```csharp
public interface IStructure
```


---


#### `ITransaction`

```csharp
public interface ITransaction : IDisposable
```

**Methods**
```csharp
public void Commit();
public void Rollback();
```


---

### Structs


#### `Dimensions`

```csharp
public struct Dimensions : IEquatable`1
```

**Properties**
```csharp
public int Height { get; set; }
public int Width { get; set; }
public Dimensions Empty { get; }
```

**Methods**
```csharp
public string ToString();
public int GetHashCode();
public bool Equals(object obj);
public bool Equals(Dimensions other);
public void Deconstruct(int Height, int Width);
```


---


#### `Location`

```csharp
public struct Location : IEquatable`1
```

**Properties**
```csharp
public int X { get; set; }
public int Y { get; set; }
public Location Empty { get; }
```

**Methods**
```csharp
public string ToString();
public int GetHashCode();
public bool Equals(object obj);
public bool Equals(Location other);
public void Deconstruct(int X, int Y);
```


---

## Namespace: `Mendix.StudioPro.ExtensionsAPI.Model.CodeActions`

### Interfaces


#### `ICodeActionParameter`

```csharp
public interface ICodeActionParameter : IElement, IStructure, IReferableStructure
```

**Properties**
```csharp
public string Name { get; set; }
public string Description { get; set; }
public string Category { get; set; }
```


---

## Namespace: `Mendix.StudioPro.ExtensionsAPI.Model.Constants`

### Interfaces


#### `IConstant`

```csharp
public interface IConstant : IDocument, IAbstractUnit, IStructure, IReferableStructure, IContextMenuStructure
```

**Properties**
```csharp
public DataType DataType { get; set; }
public IQualifiedName`1 QualifiedName { get; }
public string DefaultValue { get; set; }
public bool ExposedToClient { get; set; }
```


---

## Namespace: `Mendix.StudioPro.ExtensionsAPI.Model.DataTypes`

### Classs


#### `BinaryType`

```csharp
public sealed class BinaryType : DataType
```

**Methods**
```csharp
public string ToString();
```


---


#### `BooleanType`

```csharp
public sealed class BooleanType : DataType
```

**Methods**
```csharp
public string ToString();
```


---


#### `DataType`

```csharp
public abstract class DataType
```

**Properties**
```csharp
public BinaryType Binary { get; }
public BooleanType Boolean { get; }
public DateTimeType DateTime { get; }
public DecimalType Decimal { get; }
public EmptyType Empty { get; }
public FloatType Float { get; }
public IntegerType Integer { get; }
public StringType String { get; }
public UnknownType Unknown { get; }
public VoidType Void { get; }
```

**Methods**
```csharp
public static EnumerationType Enumeration(IQualifiedName`1 enumeration);
public static ObjectType Object(IQualifiedName`1 entity);
public static ListType List(IQualifiedName`1 entity);
```


---


#### `DateTimeType`

```csharp
public sealed class DateTimeType : DataType
```

**Methods**
```csharp
public string ToString();
```


---


#### `DecimalType`

```csharp
public sealed class DecimalType : DataType
```

**Methods**
```csharp
public string ToString();
```


---


#### `EmptyType`

```csharp
public sealed class EmptyType : DataType
```

**Methods**
```csharp
public string ToString();
```


---


#### `EntityType`

```csharp
public abstract class EntityType : DataType
```

**Properties**
```csharp
public IQualifiedName`1 EntityName { get; }
```


---


#### `EnumerationType`

```csharp
public class EnumerationType : DataType
```

**Properties**
```csharp
public IQualifiedName`1 EnumerationName { get; }
```

**Methods**
```csharp
public string ToString();
```


---


#### `FloatType`

```csharp
public sealed class FloatType : DataType
```

**Methods**
```csharp
public string ToString();
```


---


#### `IntegerType`

```csharp
public sealed class IntegerType : DataType
```

**Methods**
```csharp
public string ToString();
```


---


#### `ListType`

```csharp
public sealed class ListType : EntityType
```

**Methods**
```csharp
public string ToString();
```


---


#### `ObjectType`

```csharp
public sealed class ObjectType : EntityType
```

**Methods**
```csharp
public string ToString();
```


---


#### `StringType`

```csharp
public sealed class StringType : DataType
```

**Methods**
```csharp
public string ToString();
```


---


#### `UnknownType`

```csharp
public sealed class UnknownType : DataType
```

**Methods**
```csharp
public string ToString();
```


---


#### `VoidType`

```csharp
public sealed class VoidType : DataType
```

**Methods**
```csharp
public string ToString();
```


---

## Namespace: `Mendix.StudioPro.ExtensionsAPI.Model.DomainModels`

### Classs


#### `EntityAssociation`

```csharp
public sealed class EntityAssociation : IEquatable`1
```

**Properties**
```csharp
public IEntity Parent { get; set; }
public IEntity Child { get; set; }
public IAssociation Association { get; set; }
```

**Methods**
```csharp
public string ToString();
public int GetHashCode();
public bool Equals(object obj);
public bool Equals(EntityAssociation other);
public EntityAssociation <Clone>$();
public void Deconstruct(IEntity& Parent, IEntity& Child, IAssociation& Association);
```


---

### Enums


#### `ActionMoment`

```csharp
public enum ActionMoment : IComparable, ISpanFormattable, IFormattable, IConvertible
```

**Enum Members**
```
Before
After
```


---


#### `AssociationDirection`

```csharp
public enum AssociationDirection : IComparable, ISpanFormattable, IFormattable, IConvertible
```

**Enum Members**
```
Parent
Child
Both
```


---


#### `AssociationOwner`

```csharp
public enum AssociationOwner : IComparable, ISpanFormattable, IFormattable, IConvertible
```

**Enum Members**
```
Default
Both
```


---


#### `AssociationType`

```csharp
public enum AssociationType : IComparable, ISpanFormattable, IFormattable, IConvertible
```

**Enum Members**
```
Reference
ReferenceSet
```


---


#### `DeletingBehavior`

```csharp
public enum DeletingBehavior : IComparable, ISpanFormattable, IFormattable, IConvertible
```

**Enum Members**
```
DeleteMeAndReferences
DeleteMeButKeepReferences
DeleteMeIfNoReferences
```


---


#### `EventType`

```csharp
public enum EventType : IComparable, ISpanFormattable, IFormattable, IConvertible
```

**Enum Members**
```
Create
Commit
Delete
RollBack
```


---

### Interfaces


#### `IAssociation`

```csharp
public interface IAssociation : IElement, IStructure
```

**Properties**
```csharp
public string Name { get; set; }
public Guid DataStorageGuid { get; }
public string Documentation { get; set; }
public AssociationOwner Owner { get; set; }
public AssociationType Type { get; set; }
public DeletingBehavior ParentDeleteBehavior { get; set; }
public DeletingBehavior ChildDeleteBehavior { get; set; }
```


---


#### `IAttribute`

```csharp
public interface IAttribute : IElement, IStructure, IReferableStructure
```

**Properties**
```csharp
public Guid DataStorageGuid { get; }
public IQualifiedName`1 QualifiedName { get; }
public string Name { get; set; }
public IAttributeType Type { get; set; }
public string Documentation { get; set; }
public IValueType Value { get; set; }
```


---


#### `IAttributeType`

```csharp
public interface IAttributeType : IElement, IStructure
```


---


#### `IAutoNumberAttributeType`

```csharp
public interface IAutoNumberAttributeType : IIntegerAttributeTypeBase, INumericAttributeTypeBase, IAttributeType, IElement, IStructure
```


---


#### `IBinaryAttributeType`

```csharp
public interface IBinaryAttributeType : IAttributeType, IElement, IStructure
```


---


#### `IBooleanAttributeType`

```csharp
public interface IBooleanAttributeType : IAttributeType, IElement, IStructure
```


---


#### `ICalculatedValue`

```csharp
public interface ICalculatedValue : IValueType, IElement, IStructure
```

**Properties**
```csharp
public IQualifiedName`1 Microflow { get; set; }
public bool PassEntity { get; set; }
```


---


#### `IDateTimeAttributeType`

```csharp
public interface IDateTimeAttributeType : IAttributeType, IElement, IStructure
```

**Properties**
```csharp
public bool LocalizeDate { get; set; }
```


---


#### `IDecimalAttributeType`

```csharp
public interface IDecimalAttributeType : IDecimalAttributeTypeBase, INumericAttributeTypeBase, IAttributeType, IElement, IStructure
```


---


#### `IDecimalAttributeTypeBase`

```csharp
public interface IDecimalAttributeTypeBase : INumericAttributeTypeBase, IAttributeType, IElement, IStructure
```


---


#### `IDomainModel`

```csharp
public interface IDomainModel : IAbstractUnit, IStructure
```

**Properties**
```csharp
public string Documentation { get; set; }
```

**Methods**
```csharp
public IReadOnlyList`1 GetEntities();
public void AddEntity(IEntity entity);
public void RemoveEntity(IEntity entity);
public void InsertEntity(int index, IEntity entity);
```


---


#### `IEntity`

```csharp
public interface IEntity : IContextMenuStructure, IStructure, IElement, IReferableStructure
```

**Properties**
```csharp
public Guid DataStorageGuid { get; }
public IQualifiedName`1 QualifiedName { get; }
public string Name { get; set; }
public Location Location { get; set; }
public string Documentation { get; set; }
public IGeneralizationBase Generalization { get; set; }
```

**Methods**
```csharp
public IAssociation AddAssociation(IEntity otherEntity);
public void DeleteAssociation(IAssociation association);
public IList`1 GetAssociations(AssociationDirection direction, IEntity otherEntity);
public IReadOnlyList`1 GetAttributes();
public void AddAttribute(IAttribute attribute);
public void RemoveAttribute(IAttribute attribute);
public void InsertAttribute(int index, IAttribute attribute);
public IReadOnlyList`1 GetEventHandlers();
public void AddEventHandler(IEventHandler eventHandler);
public void RemoveEventHandler(IEventHandler eventHandler);
public void InsertEventHandler(int index, IEventHandler eventHandler);
```


---


#### `IEnumerationAttributeType`

```csharp
public interface IEnumerationAttributeType : IAttributeType, IElement, IStructure
```

**Properties**
```csharp
public IQualifiedName`1 Enumeration { get; set; }
```


---


#### `IEventHandler`

```csharp
public interface IEventHandler : IElement, IStructure
```

**Properties**
```csharp
public ActionMoment Moment { get; set; }
public EventType Event { get; set; }
public IQualifiedName`1 Microflow { get; set; }
public bool RaiseErrorOnFalse { get; set; }
public bool PassEventObject { get; set; }
```


---


#### `IGeneralization`

```csharp
public interface IGeneralization : IGeneralizationBase, IElement, IStructure
```

**Properties**
```csharp
public IQualifiedName`1 Generalization { get; set; }
```


---


#### `IGeneralizationBase`

```csharp
public interface IGeneralizationBase : IElement, IStructure
```


---


#### `IHashedStringAttributeType`

```csharp
public interface IHashedStringAttributeType : IAttributeType, IElement, IStructure
```


---


#### `IIntegerAttributeType`

```csharp
public interface IIntegerAttributeType : IIntegerAttributeTypeBase, INumericAttributeTypeBase, IAttributeType, IElement, IStructure
```


---


#### `IIntegerAttributeTypeBase`

```csharp
public interface IIntegerAttributeTypeBase : INumericAttributeTypeBase, IAttributeType, IElement, IStructure
```


---


#### `ILongAttributeType`

```csharp
public interface ILongAttributeType : IIntegerAttributeTypeBase, INumericAttributeTypeBase, IAttributeType, IElement, IStructure
```


---


#### `IMappedValue`

```csharp
public interface IMappedValue : IValueType, IElement, IStructure
```

**Properties**
```csharp
public string DefaultValueDesignTime { get; set; }
```


---


#### `INoGeneralization`

```csharp
public interface INoGeneralization : IGeneralizationBase, IElement, IStructure
```

**Properties**
```csharp
public bool HasChangedDate { get; set; }
public bool HasCreatedDate { get; set; }
public bool HasOwner { get; set; }
public bool HasChangedBy { get; set; }
public bool Persistable { get; set; }
```


---


#### `INumericAttributeTypeBase`

```csharp
public interface INumericAttributeTypeBase : IAttributeType, IElement, IStructure
```


---


#### `IStoredValue`

```csharp
public interface IStoredValue : IValueType, IElement, IStructure
```

**Properties**
```csharp
public string DefaultValue { get; set; }
```


---


#### `IStringAttributeType`

```csharp
public interface IStringAttributeType : IAttributeType, IElement, IStructure
```

**Properties**
```csharp
public int Length { get; set; }
```


---


#### `IValueType`

```csharp
public interface IValueType : IElement, IStructure
```


---

## Namespace: `Mendix.StudioPro.ExtensionsAPI.Model.Enumerations`

### Interfaces


#### `IEnumeration`

```csharp
public interface IEnumeration : IDocument, IAbstractUnit, IStructure, IReferableStructure, IContextMenuStructure
```

**Properties**
```csharp
public IQualifiedName`1 QualifiedName { get; }
```

**Methods**
```csharp
public IReadOnlyList`1 GetValues();
public void AddValue(IEnumerationValue value);
public void RemoveValue(IEnumerationValue value);
public void InsertValue(int index, IEnumerationValue value);
```


---


#### `IEnumerationValue`

```csharp
public interface IEnumerationValue : IElement, IStructure, IReferableStructure
```

**Properties**
```csharp
public IQualifiedName`1 QualifiedName { get; }
public string Name { get; set; }
public IText Caption { get; set; }
public IQualifiedName`1 Image { get; set; }
public IRemoteEnumerationValue RemoteValue { get; set; }
```


---


#### `IRemoteEnumerationValue`

```csharp
public interface IRemoteEnumerationValue : IElement, IStructure
```


---

## Namespace: `Mendix.StudioPro.ExtensionsAPI.Model.Images`

### Interfaces


#### `IImage`

```csharp
public interface IImage : IElement, IStructure, IReferableStructure
```

**Properties**
```csharp
public IQualifiedName`1 QualifiedName { get; }
public string Name { get; set; }
public Byte[] ImageData { get; set; }
```


---

## Namespace: `Mendix.StudioPro.ExtensionsAPI.Model.JavaActions`

### Interfaces


#### `IJavaAction`

```csharp
public interface IJavaAction : IDocument, IAbstractUnit, IStructure, IReferableStructure, IContextMenuStructure
```

**Properties**
```csharp
public IQualifiedName`1 QualifiedName { get; }
```

**Methods**
```csharp
public IReadOnlyList`1 GetActionParameters();
```


---


#### `IJavaActionParameter`

```csharp
public interface IJavaActionParameter : ICodeActionParameter, IElement, IStructure, IReferableStructure
```

**Properties**
```csharp
public IQualifiedName`1 QualifiedName { get; }
```


---

## Namespace: `Mendix.StudioPro.ExtensionsAPI.Model.MicroflowExpressions`

### Interfaces


#### `IMicroflowExpression`

```csharp
public interface IMicroflowExpression : IEquatable`1
```

**Properties**
```csharp
public string Text { get; }
```


---

## Namespace: `Mendix.StudioPro.ExtensionsAPI.Model.Microflows`

### Classs


#### `AggregateListFunction`

```csharp
public class AggregateListFunction : IAggregateListFunction, IElement, IStructure
```

**Properties**
```csharp
public IMicroflowExpression Expression { get; }
public IAttribute Attribute { get; }
public ReduceListFunction ReduceListFunction { get; }
```


---


#### `AssociationMemberChangeType`

```csharp
public class AssociationMemberChangeType : IMemberChangeType, IElement, IStructure
```

**Properties**
```csharp
public IAssociation Association { get; }
```


---


#### `AttributeMemberChangeType`

```csharp
public class AttributeMemberChangeType : IMemberChangeType, IElement, IStructure
```

**Properties**
```csharp
public IAttribute Attribute { get; set; }
```


---


#### `AttributeSorting`

```csharp
public class AttributeSorting : IEquatable`1
```

**Properties**
```csharp
public IAttribute Attribute { get; set; }
public bool SortByDescending { get; set; }
```

**Methods**
```csharp
public string ToString();
public int GetHashCode();
public bool Equals(object obj);
public bool Equals(AttributeSorting other);
public AttributeSorting <Clone>$();
public void Deconstruct(IAttribute& Attribute, bool SortByDescending);
```


---


#### `DatabaseRetrieveRange`

```csharp
public class DatabaseRetrieveRange : IEquatable`1
```

**Properties**
```csharp
public IMicroflowExpression OffsetExpression { get; set; }
public IMicroflowExpression AmountExpression { get; set; }
```

**Methods**
```csharp
public string ToString();
public int GetHashCode();
public bool Equals(object obj);
public bool Equals(DatabaseRetrieveRange other);
public DatabaseRetrieveRange <Clone>$();
public void Deconstruct(IMicroflowExpression& OffsetExpression, IMicroflowExpression& AmountExpression);
```


---


#### `MicroflowReturnValue`

```csharp
public class MicroflowReturnValue : IEquatable`1
```

**Properties**
```csharp
public DataType DataType { get; set; }
public IMicroflowExpression Expression { get; set; }
```

**Methods**
```csharp
public string ToString();
public int GetHashCode();
public bool Equals(object obj);
public bool Equals(MicroflowReturnValue other);
public MicroflowReturnValue <Clone>$();
public void Deconstruct(DataType& DataType, IMicroflowExpression& Expression);
```


---


#### `ReduceListFunction`

```csharp
public class ReduceListFunction
```

**Properties**
```csharp
public DataType DataType { get; }
public IMicroflowExpression InitialValueExpression { get; }
```


---

### Interfaces


#### `IActionActivity`

```csharp
public interface IActionActivity : IActivity, IMicroflowObject, IElement, IStructure
```

**Properties**
```csharp
public string Caption { get; set; }
public bool Disabled { get; set; }
public IMicroflowAction Action { get; set; }
```


---


#### `IActivity`

```csharp
public interface IActivity : IMicroflowObject, IElement, IStructure
```


---


#### `IAggregateListAction`

```csharp
public interface IAggregateListAction : IMicroflowAction, IElement, IStructure
```

**Properties**
```csharp
public IAggregateListFunction AggregateListFunction { get; set; }
public string InputListVariableName { get; set; }
public AggregateFunctionEnum AggregateFunction { get; set; }
public string OutputVariableName { get; set; }
```


---


#### `IAggregateListFunction`

```csharp
public interface IAggregateListFunction : IElement, IStructure
```

**Properties**
```csharp
public IMicroflowExpression Expression { get; }
public IAttribute Attribute { get; }
public ReduceListFunction ReduceListFunction { get; }
```


---


#### `IAssociationRetrieveSource`

```csharp
public interface IAssociationRetrieveSource : IRetrieveSource, IElement, IStructure
```

**Properties**
```csharp
public IAssociation Association { get; set; }
public string StartVariableName { get; set; }
```


---


#### `IBasicCodeActionParameterValue`

```csharp
public interface IBasicCodeActionParameterValue : IExpressionBasedCodeActionParameterValue, ICodeActionParameterValue, IElement, IStructure
```

**Properties**
```csharp
public IMicroflowExpression Argument { get; set; }
```


---


#### `IBinaryListOperation`

```csharp
public interface IBinaryListOperation : IListOperation, IElement, IStructure
```

**Properties**
```csharp
public string SecondListOrObjectVariableName { get; set; }
```


---


#### `IChangeListAction`

```csharp
public interface IChangeListAction : IMicroflowAction, IElement, IStructure
```

**Properties**
```csharp
public IMicroflowExpression Value { get; set; }
public string ChangeVariableName { get; set; }
public ChangeListActionOperation Type { get; set; }
```


---


#### `IChangeMembersAction`

```csharp
public interface IChangeMembersAction : IMicroflowAction, IElement, IStructure
```

**Properties**
```csharp
public bool RefreshInClient { get; set; }
public CommitEnum Commit { get; set; }
```

**Methods**
```csharp
public IReadOnlyList`1 GetItems();
public void AddItem(IMemberChange item);
public void RemoveItem(IMemberChange item);
public void InsertItem(int index, IMemberChange item);
```


---


#### `IChangeObjectAction`

```csharp
public interface IChangeObjectAction : IChangeMembersAction, IMicroflowAction, IElement, IStructure
```

**Properties**
```csharp
public string ChangeVariableName { get; set; }
```


---


#### `ICodeActionParameterMapping`

```csharp
public interface ICodeActionParameterMapping : IElement, IStructure
```


---


#### `ICodeActionParameterValue`

```csharp
public interface ICodeActionParameterValue : IElement, IStructure
```


---


#### `ICommitAction`

```csharp
public interface ICommitAction : IMicroflowAction, IElement, IStructure
```

**Properties**
```csharp
public bool WithEvents { get; set; }
public string CommitVariableName { get; set; }
public bool RefreshInClient { get; set; }
```


---


#### `IContains`

```csharp
public interface IContains : IBinaryListOperation, IListOperation, IElement, IStructure
```


---


#### `ICreateListAction`

```csharp
public interface ICreateListAction : IMicroflowAction, IElement, IStructure
```

**Properties**
```csharp
public IQualifiedName`1 Entity { get; set; }
public string OutputVariableName { get; set; }
```


---


#### `ICreateObjectAction`

```csharp
public interface ICreateObjectAction : IChangeMembersAction, IMicroflowAction, IElement, IStructure
```

**Properties**
```csharp
public IQualifiedName`1 Entity { get; set; }
public string OutputVariableName { get; set; }
```


---


#### `IDatabaseRetrieveSource`

```csharp
public interface IDatabaseRetrieveSource : IRetrieveSource, IElement, IStructure
```

**Properties**
```csharp
public IQualifiedName`1 Entity { get; set; }
public string XPathConstraint { get; set; }
public bool RetrieveJustFirstItem { get; set; }
public DatabaseRetrieveRange Range { get; set; }
public AttributeSorting[] AttributesToSortBy { get; set; }
```


---


#### `IDeleteAction`

```csharp
public interface IDeleteAction : IRemovesFromScope, IMicroflowAction, IElement, IStructure
```

**Properties**
```csharp
public string DeleteVariableName { get; set; }
```


---


#### `IEntityTypeCodeActionParameterValue`

```csharp
public interface IEntityTypeCodeActionParameterValue : IExpressionBasedCodeActionParameterValue, ICodeActionParameterValue, IElement, IStructure
```

**Properties**
```csharp
public IQualifiedName`1 Entity { get; set; }
```


---


#### `IExpressionBasedCodeActionParameterValue`

```csharp
public interface IExpressionBasedCodeActionParameterValue : ICodeActionParameterValue, IElement, IStructure
```


---


#### `IFilter`

```csharp
public interface IFilter : IListOperation, IElement, IStructure
```

**Properties**
```csharp
public IMicroflowExpression Expression { get; set; }
public IMemberChangeType MemberType { get; set; }
```


---


#### `IFind`

```csharp
public interface IFind : IListOperation, IElement, IStructure
```

**Properties**
```csharp
public IMicroflowExpression Expression { get; set; }
public IMemberChangeType MemberType { get; set; }
```


---


#### `IFindByExpression`

```csharp
public interface IFindByExpression : IListOperation, IElement, IStructure
```

**Properties**
```csharp
public IMicroflowExpression Expression { get; set; }
```


---


#### `IHead`

```csharp
public interface IHead : IListOperation, IElement, IStructure
```


---


#### `IIntersect`

```csharp
public interface IIntersect : IBinaryListOperation, IListOperation, IElement, IStructure
```


---


#### `IJavaActionCallAction`

```csharp
public interface IJavaActionCallAction : IMicroflowAction, IElement, IStructure
```

**Properties**
```csharp
public IQualifiedName`1 JavaAction { get; set; }
public bool UseReturnVariable { get; set; }
public string OutputVariableName { get; set; }
```

**Methods**
```csharp
public IReadOnlyList`1 GetParameterMappings();
public void RemoveParameterMapping(IJavaActionParameterMapping javaActionParameterMapping);
public void AddParameterMapping(IJavaActionParameterMapping javaActionParameterMapping);
```


---


#### `IJavaActionParameterMapping`

```csharp
public interface IJavaActionParameterMapping : ICodeActionParameterMapping, IElement, IStructure
```

**Properties**
```csharp
public IQualifiedName`1 Parameter { get; set; }
public ICodeActionParameterValue ParameterValue { get; set; }
```


---


#### `IListEquals`

```csharp
public interface IListEquals : IBinaryListOperation, IListOperation, IElement, IStructure
```


---


#### `IListOperation`

```csharp
public interface IListOperation : IElement, IStructure
```

**Properties**
```csharp
public string ListVariableName { get; set; }
```


---


#### `IListOperationAction`

```csharp
public interface IListOperationAction : IMicroflowAction, IElement, IStructure
```

**Properties**
```csharp
public IListOperation Operation { get; set; }
public string OutputVariableName { get; set; }
```


---


#### `IMemberChange`

```csharp
public interface IMemberChange : IElement, IStructure
```

**Properties**
```csharp
public IMemberChangeType MemberType { get; set; }
public IMicroflowExpression Value { get; set; }
public ChangeActionItemType Type { get; set; }
```


---


#### `IMemberChangeType`

```csharp
public interface IMemberChangeType : IElement, IStructure
```


---


#### `IMicroflow`

```csharp
public interface IMicroflow : IServerSideMicroflow, IMicroflowBase, IDocument, IAbstractUnit, IStructure, IReferableStructure, IContextMenuStructure
```

**Properties**
```csharp
public IQualifiedName`1 QualifiedName { get; }
public string Url { get; set; }
```


---


#### `IMicroflowAction`

```csharp
public interface IMicroflowAction : IElement, IStructure
```

**Methods**
```csharp
public IReadOnlyList`1 CalculateScopeVariables();
public IMicroflowExpressionContext CreateExpressionContext(DataType[] expectedTypes);
public IMicroflow GetMicroflow();
```


---


#### `IMicroflowBase`

```csharp
public interface IMicroflowBase : IDocument, IAbstractUnit, IStructure, IReferableStructure, IContextMenuStructure
```

**Properties**
```csharp
public DataType ReturnType { get; set; }
public string ReturnVariableName { get; set; }
```


---


#### `IMicroflowCall`

```csharp
public interface IMicroflowCall : IElement, IStructure
```

**Properties**
```csharp
public IQualifiedName`1 Microflow { get; set; }
```

**Methods**
```csharp
public IReadOnlyList`1 GetParameterMappings();
public void AddParameterMapping(IMicroflowCallParameterMapping parameterMapping);
public void RemoveParameterMapping(IMicroflowCallParameterMapping parameterMapping);
public void InsertParameterMapping(int index, IMicroflowCallParameterMapping parameterMapping);
```


---


#### `IMicroflowCallAction`

```csharp
public interface IMicroflowCallAction : IMicroflowAction, IElement, IStructure
```

**Properties**
```csharp
public IMicroflowCall MicroflowCall { get; set; }
public bool UseReturnVariable { get; set; }
public string OutputVariableName { get; set; }
```


---


#### `IMicroflowCallParameterMapping`

```csharp
public interface IMicroflowCallParameterMapping : IElement, IStructure
```

**Properties**
```csharp
public IQualifiedName`1 Parameter { get; set; }
public IMicroflowExpression Argument { get; set; }
```


---


#### `IMicroflowExpressionContext`

```csharp
public interface IMicroflowExpressionContext
```


---


#### `IMicroflowObject`

```csharp
public interface IMicroflowObject : IElement, IStructure
```


---


#### `IMicroflowParameterObject`

```csharp
public interface IMicroflowParameterObject : IMicroflowObject, IElement, IStructure, IReferableStructure
```

**Properties**
```csharp
public DataType Type { get; set; }
public IQualifiedName`1 QualifiedName { get; }
public string Name { get; set; }
public string Documentation { get; set; }
```


---


#### `IMicroflowParameterValue`

```csharp
public interface IMicroflowParameterValue : IExpressionBasedCodeActionParameterValue, ICodeActionParameterValue, IElement, IStructure
```

**Properties**
```csharp
public IQualifiedName`1 Microflow { get; set; }
```


---


#### `IRemovesFromScope`

```csharp
public interface IRemovesFromScope : IMicroflowAction, IElement, IStructure
```


---


#### `IRetrieveAction`

```csharp
public interface IRetrieveAction : IMicroflowAction, IElement, IStructure
```

**Properties**
```csharp
public IRetrieveSource RetrieveSource { get; set; }
public string OutputVariableName { get; set; }
```


---


#### `IRetrieveSource`

```csharp
public interface IRetrieveSource : IElement, IStructure
```


---


#### `IRollbackAction`

```csharp
public interface IRollbackAction : IMicroflowAction, IElement, IStructure
```

**Properties**
```csharp
public string RollbackVariableName { get; set; }
public bool RefreshInClient { get; set; }
```


---


#### `IRule`

```csharp
public interface IRule : IServerSideMicroflow, IMicroflowBase, IDocument, IAbstractUnit, IStructure, IReferableStructure, IContextMenuStructure
```

**Properties**
```csharp
public IQualifiedName`1 QualifiedName { get; }
```


---


#### `IServerSideMicroflow`

```csharp
public interface IServerSideMicroflow : IMicroflowBase, IDocument, IAbstractUnit, IStructure, IReferableStructure, IContextMenuStructure
```


---


#### `ISort`

```csharp
public interface ISort : IListOperation, IElement, IStructure
```

**Properties**
```csharp
public AttributeSorting[] AttributesToSortBy { get; set; }
```


---


#### `IStringTemplateParameterValue`

```csharp
public interface IStringTemplateParameterValue : ICodeActionParameterValue, IElement, IStructure
```


---


#### `ISubtract`

```csharp
public interface ISubtract : IBinaryListOperation, IListOperation, IElement, IStructure
```


---


#### `ITail`

```csharp
public interface ITail : IListOperation, IElement, IStructure
```


---


#### `IUnion`

```csharp
public interface IUnion : IBinaryListOperation, IListOperation, IElement, IStructure
```


---


#### `IVariable`

```csharp
public interface IVariable
```

**Properties**
```csharp
public string Name { get; }
public DataType DataType { get; }
```


---

## Namespace: `Mendix.StudioPro.ExtensionsAPI.Model.Microflows.Actions`

### Enums


#### `AggregateFunctionEnum`

```csharp
public enum AggregateFunctionEnum : IComparable, ISpanFormattable, IFormattable, IConvertible
```

**Enum Members**
```
Sum
Average
Count
Minimum
Maximum
All
Any
Reduce
```


---


#### `ChangeActionItemType`

```csharp
public enum ChangeActionItemType : IComparable, ISpanFormattable, IFormattable, IConvertible
```

**Enum Members**
```
Set
Add
Remove
```


---


#### `ChangeListActionOperation`

```csharp
public enum ChangeListActionOperation : IComparable, ISpanFormattable, IFormattable, IConvertible
```

**Enum Members**
```
Set
Add
Remove
Clear
```


---


#### `CommitEnum`

```csharp
public enum CommitEnum : IComparable, ISpanFormattable, IFormattable, IConvertible
```

**Enum Members**
```
Yes
YesWithoutEvents
No
```


---

## Namespace: `Mendix.StudioPro.ExtensionsAPI.Model.Pages`

### Interfaces


#### `IPage`

```csharp
public interface IPage : IDocument, IAbstractUnit, IStructure, IReferableStructure, IContextMenuStructure
```


---

## Namespace: `Mendix.StudioPro.ExtensionsAPI.Model.Projects`

### Interfaces


#### `IDocument`

```csharp
public interface IDocument : IAbstractUnit, IStructure, IReferableStructure, IContextMenuStructure
```

**Properties**
```csharp
public string Name { get; set; }
public bool Excluded { get; set; }
```


---


#### `IFolder`

```csharp
public interface IFolder : IFolderBase, IAbstractUnit, IStructure
```

**Properties**
```csharp
public string Name { get; set; }
```


---


#### `IFolderBase`

```csharp
public interface IFolderBase : IAbstractUnit, IStructure
```

**Methods**
```csharp
public IReadOnlyList`1 GetDocuments();
public void RemoveDocument(IDocument document);
public void AddDocument(IDocument document);
public IReadOnlyList`1 GetFolders();
public void RemoveFolder(IFolder folder);
public void AddFolder(IFolder folder);
```


---


#### `IModule`

```csharp
public interface IModule : IFolderBase, IAbstractUnit, IStructure, IReferableStructure
```

**Properties**
```csharp
public IQualifiedName`1 QualifiedName { get; }
public string Name { get; set; }
public IDomainModel DomainModel { get; }
public bool FromAppStore { get; set; }
public string AppStorePackageId { get; set; }
public string AppStoreVersionGuid { get; set; }
public string AppStoreVersion { get; set; }
```


---


#### `IProject`

```csharp
public interface IProject : IAbstractUnit, IStructure
```

**Properties**
```csharp
public string Name { get; }
public string DirectoryPath { get; }
```

**Methods**
```csharp
public IReadOnlyList`1 GetModules();
public void AddModule(IModule module);
public IReadOnlyList`1 GetProjectDocuments();
public Dictionary`2 GetDocuments();
public Dictionary`2 GetDocuments();
public Dictionary`2 GetDocuments(Type documentType);
public IReadOnlyList`1 GetModuleDocuments(IModule module);
public IReadOnlyList`1 GetModuleDocuments(IModule module);
public IReadOnlyList`1 GetModuleDocuments(IModule module, Type documentType);
```


---


#### `IProjectDocument`

```csharp
public interface IProjectDocument : IAbstractUnit, IStructure
```


---

## Namespace: `Mendix.StudioPro.ExtensionsAPI.Model.Settings`

### Interfaces


#### `IConfiguration`

```csharp
public interface IConfiguration : IElement, IStructure
```

**Properties**
```csharp
public string Name { get; set; }
public string ApplicationRootUrl { get; set; }
```

**Methods**
```csharp
public IReadOnlyList`1 GetCustomSettings();
public void AddCustomSetting(ICustomSetting customSetting);
public void RemoveCustomSetting(ICustomSetting customSetting);
public void InsertCustomSetting(int index, ICustomSetting customSetting);
public IReadOnlyList`1 GetConstantValues();
public void AddConstantValue(IConstantValue constantValue);
public void RemoveConstantValue(IConstantValue constantValue);
public void InsertConstantValue(int index, IConstantValue constantValue);
```


---


#### `IConfigurationSettings`

```csharp
public interface IConfigurationSettings : IProjectSettingsPart, IElement, IStructure
```

**Methods**
```csharp
public IReadOnlyList`1 GetConfigurations();
public void AddConfiguration(IConfiguration configuration);
public void RemoveConfiguration(IConfiguration configuration);
public void InsertConfiguration(int index, IConfiguration configuration);
```


---


#### `IConstantValue`

```csharp
public interface IConstantValue : IElement, IStructure
```

**Properties**
```csharp
public SecretManagerKey SecretManagerKey { get; }
public IQualifiedName`1 Constant { get; set; }
public ISharedOrPrivateValue SharedOrPrivateValue { get; set; }
```


---


#### `ICustomSetting`

```csharp
public interface ICustomSetting : IElement, IStructure
```

**Properties**
```csharp
public string Name { get; set; }
public string Value { get; set; }
```


---


#### `IPrivateValue`

```csharp
public interface IPrivateValue : ISharedOrPrivateValue, IElement, IStructure
```


---


#### `IProjectSettings`

```csharp
public interface IProjectSettings : IProjectDocument, IAbstractUnit, IStructure
```

**Methods**
```csharp
public IReadOnlyList`1 GetSettingsParts();
```


---


#### `IProjectSettingsPart`

```csharp
public interface IProjectSettingsPart : IElement, IStructure
```


---


#### `IRuntimeSettings`

```csharp
public interface IRuntimeSettings : IProjectSettingsPart, IElement, IStructure
```

**Properties**
```csharp
public IQualifiedName`1 AfterStartupMicroflow { get; set; }
public IQualifiedName`1 BeforeShutdownMicroflow { get; set; }
public IQualifiedName`1 HealthCheckMicroflow { get; set; }
```


---


#### `ISharedOrPrivateValue`

```csharp
public interface ISharedOrPrivateValue : IElement, IStructure
```


---


#### `ISharedValue`

```csharp
public interface ISharedValue : ISharedOrPrivateValue, IElement, IStructure
```

**Properties**
```csharp
public string Value { get; set; }
```


---

## Namespace: `Mendix.StudioPro.ExtensionsAPI.Model.Texts`

### Interfaces


#### `IText`

```csharp
public interface IText : IElement, IStructure
```

**Methods**
```csharp
public IReadOnlyList`1 GetTranslations();
public void AddOrUpdateTranslation(string languageCode, string text);
public void RemoveTranslation(string languageCode);
```


---


#### `ITranslation`

```csharp
public interface ITranslation : IElement, IStructure
```

**Properties**
```csharp
public string LanguageCode { get; }
public string Text { get; set; }
```


---

## Namespace: `Mendix.StudioPro.ExtensionsAPI.Model.UntypedModel`

### Enums


#### `PropertyType`

```csharp
public enum PropertyType : IComparable, ISpanFormattable, IFormattable, IConvertible
```

**Enum Members**
```
Boolean
Integer
Double
DateTime
String
Guid
Location
Dimensions
Color
Blob
Element
ElementByName
ElementLocalByName
ElementByID
Enumeration
```


---

### Interfaces


#### `IModelElement`

```csharp
public interface IModelElement : IModelStructure
```


---


#### `IModelProperty`

```csharp
public interface IModelProperty
```

**Properties**
```csharp
public string Name { get; }
public PropertyType Type { get; }
public bool IsList { get; }
public object Value { get; }
```

**Methods**
```csharp
public IReadOnlyList`1 GetValues();
```


---


#### `IModelRoot`

```csharp
public interface IModelRoot
```

**Methods**
```csharp
public IReadOnlyList`1 GetUnitsOfType(string unitType);
```


---


#### `IModelStructure`

```csharp
public interface IModelStructure
```

**Properties**
```csharp
public Guid ID { get; }
public string Type { get; }
public string Name { get; }
public string QualifiedName { get; }
```

**Methods**
```csharp
public IReadOnlyList`1 GetProperties();
public IModelProperty GetProperty(string name);
public IReadOnlyList`1 GetElements();
public IReadOnlyList`1 GetElementsOfType(string elementType);
```


---


#### `IModelUnit`

```csharp
public interface IModelUnit : IModelStructure
```

**Methods**
```csharp
public IReadOnlyList`1 GetUnits();
public IReadOnlyList`1 GetUnitsOfType(string unitType);
```


---

## Namespace: `Mendix.StudioPro.ExtensionsAPI.Services`

### Classs


#### `SecretManagerKey`

```csharp
public class SecretManagerKey : IEquatable`1
```

**Properties**
```csharp
public string Category { get; set; }
public string Identifier { get; set; }
```

**Methods**
```csharp
public string ToString();
public int GetHashCode();
public bool Equals(object obj);
public bool Equals(SecretManagerKey other);
public SecretManagerKey <Clone>$();
public void Deconstruct(string Category, string Identifier);
```


---


#### `ValidationResult`

```csharp
public sealed class ValidationResult : IEquatable`1
```

**Properties**
```csharp
public bool IsValid { get; set; }
public string ErrorMessage { get; set; }
```

**Methods**
```csharp
public string ToString();
public int GetHashCode();
public bool Equals(object obj);
public bool Equals(ValidationResult other);
public ValidationResult <Clone>$();
public void Deconstruct(bool IsValid, string ErrorMessage);
```


---

### Interfaces


#### `IBackgroundJobService`

```csharp
public interface IBackgroundJobService
```

**Methods**
```csharp
public bool Run(BackgroundJob job);
```


---


#### `IConfigurationService`

```csharp
public interface IConfigurationService
```

**Properties**
```csharp
public IConfiguration Configuration { get; }
```


---


#### `IDomainModelService`

```csharp
public interface IDomainModelService
```

**Methods**
```csharp
public IList`1 GetAllAssociations(IModel currentApp, IModule[] modules);
public IList`1 GetAssociationsBetweenEntities(IModel currentApp, IEntity parent, IEntity child);
public IList`1 GetAnyAssociationsBetweenEntities(IModel currentApp, IEntity entity1, IEntity entity2);
public IList`1 GetAssociationsOfEntity(IModel currentApp, IEntity entity, AssociationDirection associationDirection);
```


---


#### `IExtensionFeaturesService`

```csharp
public interface IExtensionFeaturesService
```

**Methods**
```csharp
public void DisableExtension(ExtensionBase extension);
public bool IsDisabled(ExtensionBase extension);
```


---


#### `IExtensionFileService`

```csharp
public interface IExtensionFileService
```

**Methods**
```csharp
public string ResolvePath(string pathSegments);
```


---


#### `IHttpClientService`

```csharp
public interface IHttpClientService
```

**Methods**
```csharp
public IHttpClient CreateHttpClient();
```


---


#### `ILogService`

```csharp
public interface ILogService
```

**Methods**
```csharp
public void Debug(string message, string memberName, string filePath);
public void Info(string message, string memberName, string filePath);
public void Warn(string message, string memberName, string filePath);
public void Error(string message, Exception exception, string memberName, string filePath);
```


---


#### `IMicroflowActivitiesService`

```csharp
public interface IMicroflowActivitiesService
```

**Methods**
```csharp
public IActionActivity CreateCreateObjectActivity(IModel model, IEntity entity, string outputVariableName, CommitEnum commit, bool refreshInClient, ValueTuple`2[] initialValues);
public IActionActivity CreateChangeAttributeActivity(IModel model, IAttribute attribute, ChangeActionItemType changeType, IMicroflowExpression newValueExpression, string changeVariableName, CommitEnum commit);
public IActionActivity CreateChangeAssociationActivity(IModel model, IAssociation association, ChangeActionItemType changeType, IMicroflowExpression newValueExpression, string changeVariableName, CommitEnum commit);
public IActionActivity CreateCommitObjectActivity(IModel model, string commitVariableName, bool withEvents, bool refreshInClient);
public IActionActivity CreateRollbackObjectActivity(IModel model, string rollbackVariableName, bool refreshInClient);
public IActionActivity CreateDeleteObjectActivity(IModel model, string deleteVariableName);
public IActionActivity CreateDatabaseRetrieveSourceActivity(IModel model, string outputVariableName, IEntity entity, string xPathConstraint, ValueTuple`2 range, AttributeSorting[] attributesToSortBy);
public IActionActivity CreateDatabaseRetrieveSourceActivity(IModel model, string outputVariableName, IEntity entity, string xPathConstraint, bool retrieveJustFirstItem, AttributeSorting[] attributesToSortBy);
public IActionActivity CreateAssociationRetrieveSourceActivity(IModel model, IAssociation association, string outputVariableName, string entityVariableName);
public IActionActivity CreateCreateListActivity(IModel model, IEntity entity, string outputVariableName);
public IActionActivity CreateChangeListActivity(IModel model, ChangeListActionOperation operation, string listVariableName, IMicroflowExpression changeValueExpression);
public IActionActivity CreateSortListActivity(IModel model, string listVariableName, string outputVariableName, AttributeSorting[] attributesToSortBy);
public IActionActivity CreateFilterListByAssociationActivity(IModel model, IAssociation association, string listVariableName, string outputVariableName, IMicroflowExpression filterExpression);
public IActionActivity CreateFilterListByAttributeActivity(IModel model, IAttribute attribute, string listVariableName, string outputVariableName, IMicroflowExpression filterExpression);
public IActionActivity CreateFindByExpressionActivity(IModel model, string listVariableName, string outputVariableName, IMicroflowExpression findExpression);
public IActionActivity CreateFindByAttributeActivity(IModel model, IAttribute attribute, string listVariableName, string outputVariableName, IMicroflowExpression findExpression);
public IActionActivity CreateFindByAssociationActivity(IModel model, IAssociation association, string listVariableName, string outputVariableName, IMicroflowExpression findExpression);
public IActionActivity CreateListOperationActivity(IModel model, string listVariableName, string outputVariableName, IListOperation listOperation);
public IActionActivity CreateAggregateListActivity(IModel model, string inputListVariableName, string outputVariableName, AggregateFunctionEnum aggregateFunction);
public IActionActivity CreateAggregateListByExpressionActivity(IModel model, IMicroflowExpression expression, string inputListVariableName, string outputVariableName, AggregateFunctionEnum aggregateFunction);
public IActionActivity CreateAggregateListByAttributeActivity(IModel model, IAttribute attribute, string inputListVariableName, string outputVariableName, AggregateFunctionEnum aggregateFunction);
public IActionActivity CreateReduceAggregateActivity(IModel model, string inputListVariableName, string outputVariableName, IMicroflowExpression initialValueExpression, IMicroflowExpression expression, DataType dataType);
```


---


#### `IMicroflowExpressionService`

```csharp
public interface IMicroflowExpressionService
```

**Methods**
```csharp
public IMicroflowExpression CreateFromString(string value);
public bool TryGetComputedType(IModel model, IMicroflowExpression microflowExpression, DataType& dataType);
```


---


#### `IMicroflowService`

```csharp
public interface IMicroflowService
```

**Methods**
```csharp
public void Initialize(IMicroflow microflow, ValueTuple`2[] parameters);
public IMicroflow CreateMicroflow(IModel model, IFolderBase container, string name, MicroflowReturnValue returnValue, ValueTuple`2[] parameters);
public bool TryInsertAfterStart(IMicroflow microflow, IActivity[] activities);
public bool TryInsertBeforeActivity(IActivity insertBeforeActivity, IActivity[] activities);
public IReadOnlyList`1 GetParameters(IMicroflow microflow);
public IReadOnlyList`1 GetAllMicroflowActivities(IMicroflow microflow);
public void UpdateActionAfterRename(IModel model, IMicroflowAction microflowAction, Func`1 rename);
public bool IsVariableNameInUse(IMicroflow microflow, string variableName);
```


---


#### `INameValidationService`

```csharp
public interface INameValidationService
```

**Methods**
```csharp
public string GetValidName(string candidateName);
public ValidationResult IsNameValid(string name);
```


---


#### `INavigationManagerService`

```csharp
public interface INavigationManagerService
```

**Methods**
```csharp
public void PopulateWebNavigationWith(IModel model, ValueTuple`2[] pages);
```


---


#### `IPageGenerationService`

```csharp
public interface IPageGenerationService
```

**Methods**
```csharp
public IEnumerable`1 GenerateOverviewPages(IModule module, IEnumerable`1 entities, bool generateIndexSnippet);
```


---


#### `IUntypedModelAccessService`

```csharp
public interface IUntypedModelAccessService
```

**Methods**
```csharp
public IModelRoot GetUntypedModel(IModel model);
```


---

## Namespace: `Mendix.StudioPro.ExtensionsAPI.UI`

### Classs


#### `UIExtensionBase`

```csharp
public abstract class UIExtensionBase : ExtensionBase
```


---


#### `ViewModelBase`

```csharp
public abstract class ViewModelBase : INotifyPropertyChanged
```


---

### Interfaces


#### `IContextMenuStructure`

```csharp
public interface IContextMenuStructure : IStructure
```


---

## Namespace: `Mendix.StudioPro.ExtensionsAPI.UI.Dialogs`

### Classs


#### `ModalDialogViewModelBase`

```csharp
public abstract class ModalDialogViewModelBase : ViewModelBase, INotifyPropertyChanged
```

**Properties**
```csharp
public string Title { get; }
public Nullable`1 Height { get; set; }
public Nullable`1 Width { get; set; }
public Action OnClosed { get; set; }
public Action`1 OnClosing { get; set; }
```


---


#### `WebViewModalDialogViewModel`

```csharp
public abstract class WebViewModalDialogViewModel : ModalDialogViewModelBase, INotifyPropertyChanged
```

**Methods**
```csharp
public void InitWebView(IWebView webView);
```


---

## Namespace: `Mendix.StudioPro.ExtensionsAPI.UI.DockablePane`

### Classs


#### `DockablePaneExtension`

```csharp
public abstract class DockablePaneExtension : UIExtensionBase
```

**Properties**
```csharp
public string Id { get; }
public DockablePanePosition InitialPosition { get; }
```

**Methods**
```csharp
public DockablePaneViewModelBase Open();
```


---


#### `DockablePaneViewModelBase`

```csharp
public abstract class DockablePaneViewModelBase : ViewModelBase, INotifyPropertyChanged
```

**Properties**
```csharp
public Action OnClosed { get; set; }
public Action OnActivated { get; set; }
public string Title { get; set; }
public bool IsBadgeVisible { get; set; }
public int BadgeValue { get; set; }
public DockablePaneBadgePriority BadgePriority { get; set; }
```


---


#### `WebViewDockablePaneViewModel`

```csharp
public abstract class WebViewDockablePaneViewModel : DockablePaneViewModelBase, INotifyPropertyChanged
```

**Methods**
```csharp
public void InitWebView(IWebView webView);
```


---

### Enums


#### `DockablePaneBadgePriority`

```csharp
public enum DockablePaneBadgePriority : IComparable, ISpanFormattable, IFormattable, IConvertible
```

**Enum Members**
```
Normal
High
```


---


#### `DockablePanePosition`

```csharp
public enum DockablePanePosition : IComparable, ISpanFormattable, IFormattable, IConvertible
```

**Enum Members**
```
Left
Right
Bottom
```


---

## Namespace: `Mendix.StudioPro.ExtensionsAPI.UI.Events`

### Classs


#### `ActiveDocumentChanged`

```csharp
public class ActiveDocumentChanged : IEvent
```

**Properties**
```csharp
public string DocumentName { get; }
public string DocumentType { get; }
```

**Methods**
```csharp
public IAbstractUnit GetDocument(IProject project);
```


---


#### `ExtensionLoaded`

```csharp
public sealed class ExtensionLoaded : IEvent
```


---


#### `ExtensionUnloading`

```csharp
public sealed class ExtensionUnloading : IEvent
```


---

### Interfaces


#### `IEvent`

```csharp
public interface IEvent
```


---


#### `IEventSubscription`

```csharp
public interface IEventSubscription
```


---

## Namespace: `Mendix.StudioPro.ExtensionsAPI.UI.Menu`

### Classs


#### `ContextMenuExtension`1`

```csharp
public abstract class ContextMenuExtension`1 : UIExtensionBase, IContextMenuExtension
```

**Properties**
```csharp
public Type StructureType { get; }
```

**Methods**
```csharp
public IEnumerable`1 GetContextMenus(TElement element);
```


---


#### `MenuExtension`

```csharp
public abstract class MenuExtension : UIExtensionBase
```

**Methods**
```csharp
public IEnumerable`1 GetMenus();
```


---


#### `MenuViewModel`

```csharp
public sealed class MenuViewModel : ViewModelBase, INotifyPropertyChanged
```

**Properties**
```csharp
public MenuSeparator Separator { get; set; }
public string Caption { get; set; }
public bool IsEnabled { get; set; }
public Action MenuAction { get; set; }
public IEnumerable`1 SubMenus { get; }
```


---

### Enums


#### `MenuSeparator`

```csharp
public enum MenuSeparator : IComparable, ISpanFormattable, IFormattable, IConvertible
```

**Enum Members**
```
None
After
Before
Both
```


---

## Namespace: `Mendix.StudioPro.ExtensionsAPI.UI.Microflows`

### Classs


#### `EditMicroflowExpressionResult`

```csharp
public sealed class EditMicroflowExpressionResult
```

**Properties**
```csharp
public bool IsCanceled { get; }
public IMicroflowExpression Expression { get; }
```


---

## Namespace: `Mendix.StudioPro.ExtensionsAPI.UI.Services`

### Classs


#### `DocumentSelectorDialogOptions`1`

```csharp
public sealed class DocumentSelectorDialogOptions`1 : SelectorDialogOptions`2
```


---


#### `EntitySelectorDialogOptions`

```csharp
public sealed class EntitySelectorDialogOptions : SelectorDialogOptions`2
```


---


#### `SelectorDialogOptions`2`

```csharp
public abstract class SelectorDialogOptions`2
```

**Properties**
```csharp
public IAbstractUnit Context { get; }
public TStructure InitialSelection { get; }
public bool AllowNone { get; set; }
public Func`2 Filter { get; set; }
public Func`2 CreateElement { get; set; }
```


---


#### `SelectorResult`1`

```csharp
public sealed class SelectorResult`1
```

**Properties**
```csharp
public bool IsCanceled { get; }
public TStructure Selection { get; }
```


---

### Interfaces


#### `IAppService`

```csharp
public interface IAppService
```

**Methods**
```csharp
public Task`1 GetOnlineAppIDForCurrentAppAsync();
public bool TryImportApp(IModel model, string mpkFilePath, string name);
public bool CheckVersionCompatible(IModel model, string mendixVersion, string mismatchMessage);
public bool TryImportModule(IModel model, string moduleMpkPath, string versionId, string version, string packageId);
public void SynchronizeWithFileSystem(IModel model);
```


---


#### `IDialogService`

```csharp
public interface IDialogService
```

**Methods**
```csharp
public void ShowDialog(ModalDialogViewModelBase dialog);
public void CloseDialog(ModalDialogViewModelBase dialog);
```


---


#### `IDockingWindowService`

```csharp
public interface IDockingWindowService
```

**Methods**
```csharp
public void OpenTab(TabViewModelBase tab);
public void CloseTab(TabViewModelBase tab);
public void OpenPane(string paneId);
public void ClosePane(string paneId);
public bool TryOpenEditor(IAbstractUnit unit, IElement elementToFocus);
public bool TryGetActiveEditor(IModel model, IAbstractUnit& unit);
```


---


#### `IEntityService`

```csharp
public interface IEntityService
```

**Methods**
```csharp
public bool OpenEntityForm(IEntity entity);
```


---


#### `IFindResultsPaneService`

```csharp
public interface IFindResultsPaneService
```

**Methods**
```csharp
public void ShowUsagesOf(IReferableStructure referableStructure);
```


---


#### `ILocalRunConfigurationsService`

```csharp
public interface ILocalRunConfigurationsService
```

**Methods**
```csharp
public IConfiguration GetActiveConfiguration(IModel model);
```


---


#### `IMessageBoxService`

```csharp
public interface IMessageBoxService
```

**Methods**
```csharp
public void ShowError(string message, string details, string linkText, Uri linkUri);
public void ShowInformation(string message, string details, string linkText, Uri linkUri);
public void ShowWarning(string message, string details, string linkText, Uri linkUri);
public string ShowQuestion(string question, string details, string buttons, string defaultButton);
```


---


#### `IMicroflowExpressionEditorService`

```csharp
public interface IMicroflowExpressionEditorService
```

**Methods**
```csharp
public EditMicroflowExpressionResult ShowExpressionEditor(string title, IMicroflowExpression expression, IMicroflowExpressionContext expressionContext);
```


---


#### `INotificationPopupService`

```csharp
public interface INotificationPopupService
```

**Methods**
```csharp
public void ShowNotification(string title, string message, StudioProImage image, Nullable`1 timeout);
```


---


#### `IRuntimeService`

```csharp
public interface IRuntimeService
```

**Methods**
```csharp
public Nullable`1 ExecutePreviewAction(string actionName, IDictionary`2 parameters);
```


---


#### `ISelectorDialogService`

```csharp
public interface ISelectorDialogService
```

**Methods**
```csharp
public Task`1 SelectDocumentAsync(DocumentSelectorDialogOptions`1 options);
public Task`1 SelectDocumentUntypedAsync(DocumentSelectorDialogOptions`1 options);
public Task`1 SelectEntityAsync(EntitySelectorDialogOptions options);
```


---


#### `IVersionControlService`

```csharp
public interface IVersionControlService
```

**Methods**
```csharp
public IBranch GetCurrentBranch(IModel app);
public ICommit GetHeadCommit(IModel app, IBranch branch);
public bool IsProjectVersionControlled(IModel app);
```


---

## Namespace: `Mendix.StudioPro.ExtensionsAPI.UI.Tab`

### Classs


#### `TabViewModelBase`

```csharp
public abstract class TabViewModelBase : ViewModelBase, INotifyPropertyChanged
```

**Properties**
```csharp
public Action OnClosed { get; set; }
public string Title { get; set; }
public StudioProImage Icon { get; set; }
```


---


#### `WebViewTabViewModel`

```csharp
public abstract class WebViewTabViewModel : TabViewModelBase, INotifyPropertyChanged
```

**Methods**
```csharp
public void InitWebView(IWebView webView);
```


---

## Namespace: `Mendix.StudioPro.ExtensionsAPI.UI.WebServer`

### Classs


#### `HandleWebRequestAsync`

```csharp
public sealed class HandleWebRequestAsync : MulticastDelegate, ICloneable, ISerializable
```

**Methods**
```csharp
public Task Invoke(HttpListenerRequest request, HttpListenerResponse response, CancellationToken cancellationToken);
public IAsyncResult BeginInvoke(HttpListenerRequest request, HttpListenerResponse response, CancellationToken cancellationToken, AsyncCallback callback, object object);
public Task EndInvoke(IAsyncResult result);
```


---


#### `WebServerExtension`

```csharp
public abstract class WebServerExtension : UIExtensionBase
```

**Methods**
```csharp
public void InitializeWebServer(IWebServer webServer);
```


---

### Interfaces


#### `IWebServer`

```csharp
public interface IWebServer
```

**Methods**
```csharp
public void AddRoute(string urlPrefix, HandleWebRequestAsync requestHandler);
```


---

## Namespace: `Mendix.StudioPro.ExtensionsAPI.UI.WebView`

### Classs


#### `MessageReceivedEventArgs`

```csharp
public sealed class MessageReceivedEventArgs : EventArgs
```

**Properties**
```csharp
public string Message { get; }
public JsonObject Data { get; }
```


---

### Interfaces


#### `IWebView`

```csharp
public interface IWebView
```

**Properties**
```csharp
public Uri Address { get; set; }
```

**Methods**
```csharp
public void ShowDevTools();
public void Reload(bool ignoreCache);
public void PostMessage(string message, object data);
```


---

## Namespace: `Mendix.StudioPro.ExtensionsAPI.VersionControl`

### Interfaces


#### `IBranch`

```csharp
public interface IBranch
```

**Properties**
```csharp
public string Name { get; }
```


---


#### `ICommit`

```csharp
public interface ICommit
```

**Properties**
```csharp
public string ID { get; }
public string Author { get; }
public string Date { get; }
public string Message { get; }
```


---
