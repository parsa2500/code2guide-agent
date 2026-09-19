using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace SampleApi.Entities;

[Table("Tenders")]
public class Tender
{
    public int Id { get; set; }

    [Required]
    public string Title { get; set; } = string.Empty;

    public string? Description { get; set; }

    public string Status { get; set; } = "Draft";

    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    [ForeignKey("CreatedByUser")]
    public int? CreatedByUserId { get; set; }

    public virtual User? CreatedByUser { get; set; }
}

[Table("Users")]
public class User
{
    public int Id { get; set; }

    [Required]
    public string UserName { get; set; } = string.Empty;

    public virtual ICollection<Tender> Tenders { get; set; } = new List<Tender>();
}
