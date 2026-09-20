using System;
using System.ComponentModel.DataAnnotations.Schema;

namespace Contracts.Models.BussinessEntities
{
    [Table("Contracts")]
    public class Contract
    {
        public Guid Id { get; set; }
        public string Title { get; set; }
        public string ContractNumber { get; set; }
        public Guid ContractorID { get; set; }
        public bool Deleted { get; set; }
    }
}
